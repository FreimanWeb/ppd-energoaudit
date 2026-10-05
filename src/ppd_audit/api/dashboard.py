"""Чтение данных для отдельного frontend без зависимости от Streamlit."""

from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

from ..config import load_constraints
from ..core.losses import build_loss_map
from ..db import AuditDatabase
from ..services.result_scope import result_scope
from ..services.telemetry_audit import object_from_database, run_snapshot_audit, telemetry_snapshots
from .contracts import (
    AggregateSummary,
    SnapshotAuditRequest,
    SnapshotAuditResponse,
    SnapshotResponse,
    TelemetryDates,
    TopologyResponse,
)


router = APIRouter()


def _database() -> AuditDatabase:
    # Общий bootstrap и конфигурация подключения остаются у API entrypoint.
    from .main import _database as database

    return database()


def _require_ids(database: AuditDatabase, object_id: str, aggregate_id: str | None = None):
    try:
        plant = database.plant(object_id)
        if aggregate_id is not None:
            database.aggregate(object_id, aggregate_id)
        return plant
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc


def _day_window(day: str) -> tuple[datetime, datetime]:
    try:
        parsed = date.fromisoformat(day)
        if parsed.isoformat() != day:
            raise ValueError("дата должна иметь формат YYYY-MM-DD")
        start = datetime.combine(parsed, time.min)
        return start, start + timedelta(days=1)
    except ValueError as exc:
        raise HTTPException(400, detail="дата должна иметь формат YYYY-MM-DD") from exc


def _snapshot_response(snapshot) -> dict:
    return {
        "timestamp": snapshot.timestamp.isoformat(),
        "p_in_mpa": snapshot.p_in_mpa,
        "p_out_mpa": snapshot.p_out_mpa,
        "p_bg_mpa": snapshot.p_bg_mpa,
        "power_kw": snapshot.power_kw,
    }


@router.get("/objects/{object_id}/aggregates", response_model=list[AggregateSummary])
def aggregates(object_id: str) -> list[dict]:
    database = _database()
    _require_ids(database, object_id)
    result = []
    for aggregate in database.aggregates(object_id):
        dates = database.telemetry_dates(object_id, aggregate["code"])
        at = datetime.combine(dates[-1], time.min) if dates else datetime.now()
        try:
            passport = database.active_passport(object_id, aggregate["code"], at)
            pump_model = passport["pump_model"]
        except KeyError:
            pump_model = None
        result.append({**aggregate, "pump_model": pump_model, "has_telemetry": bool(dates)})
    return result


@router.get(
    "/objects/{object_id}/aggregates/{aggregate_id}/dates",
    response_model=TelemetryDates,
)
def dates(object_id: str, aggregate_id: str) -> dict:
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    days = database.telemetry_dates(object_id, aggregate_id)
    default = database.last_day_with_daily_totals(object_id, aggregate_id)
    default = default or (days[-1] if days else None)
    return {
        "dates": [day.isoformat() for day in days],
        "default_date": default.isoformat() if default else None,
    }


@router.get(
    "/objects/{object_id}/aggregates/{aggregate_id}/snapshots",
    response_model=list[SnapshotResponse],
)
def snapshots(object_id: str, aggregate_id: str, day: str) -> list[dict]:
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    start, end = _day_window(day)
    try:
        return [
            _snapshot_response(snapshot)
            for snapshot in telemetry_snapshots(database, object_id, aggregate_id, start, end)
        ]
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.get("/objects/{object_id}/topology", response_model=TopologyResponse)
def topology(object_id: str) -> dict:
    database = _database()
    plant = _require_ids(database, object_id)
    path = Path(__file__).resolve().parents[3] / "config" / "topology" / f"{object_id}.yaml"
    aggregate_codes = {item["code"] for item in database.aggregates(object_id)}
    if path.exists():
        graph = yaml.safe_load(path.read_text(encoding="utf-8"))
        for node in graph["nodes"]:
            if node["type"] == "pump" and not node.get("agg"):
                if node["label"] in aggregate_codes:
                    node["agg"] = node["label"]
        return {**graph, "is_typical": False}

    nodes = [{"id": "src", "type": "source", "x": 0, "y": 0, "label": "Приём воды"}]
    edges = []
    aggregate_list = aggregates(object_id)
    for index, aggregate in enumerate(aggregate_list):
        node_id = f"pump-{index}"
        nodes.append({
            "id": node_id,
            "type": "pump",
            "x": 1,
            "y": (len(aggregate_list) - 1) / 2 - index,
            "label": aggregate["code"],
            "agg": aggregate["code"],
            "sub": aggregate["pump_model"],
        })
        edges.extend([{"from": "src", "to": node_id}, {"from": node_id, "to": "man"}])
    for index, (node_id, kind, label) in enumerate(
        [
            ("man", "meter", "Выход из станции"),
            ("comb", "manifold", "Блок гребёнок"),
            ("valve", "valve", "ЗРА / штуцеры"),
            ("wells", "wells", "Нагнетательные скважины"),
            ("res", "reservoir", "Пласт / призабойная зона"),
        ],
        start=2,
    ):
        nodes.append({"id": node_id, "type": kind, "x": index, "y": 0, "label": label})
    edges.extend([
        {"from": "man", "to": "comb"},
        {"from": "comb", "to": "valve"},
        {"from": "valve", "to": "wells", "kind": "throttle"},
        {"from": "wells", "to": "res"},
    ])
    return {
        "title": plant["name"],
        "source": "Типовая схема по составу агрегатов; обвязка не подтверждена",
        "is_typical": True,
        "nodes": nodes,
        "edges": edges,
    }


@router.post(
    "/objects/{object_id}/aggregates/{aggregate_id}/snapshot-audit",
    response_model=SnapshotAuditResponse,
)
def snapshot_audit(object_id: str, aggregate_id: str, request: SnapshotAuditRequest) -> dict:
    from .main import _to_response

    database = _database()
    _require_ids(database, object_id, aggregate_id)
    start, end = _day_window(request.day)
    try:
        timestamp = datetime.fromisoformat(request.timestamp)
        if timestamp.tzinfo is not None:
            raise ValueError("телеметрия использует локальное время без UTC offset")
        if not start <= timestamp < end:
            raise ValueError("снимок должен принадлежать выбранным суткам")
        result = run_snapshot_audit(
            database,
            object_id,
            aggregate_id,
            start,
            end,
            timestamp,
            track_clarifications=False,
        )
        obj = object_from_database(database, object_id, start, aggregate_code=aggregate_id)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    regime = result.audit.spec.regime
    scope = result_scope(
        regime,
        None if result.annual_runtime_is_assumed else regime.t_year,
    )
    losses = []
    if result.quality.allows_economic_conclusions:
        tariff = load_constraints().economics.get("tariff_rub_kwh", 4.68)
        losses = [asdict(item) for item in build_loss_map(result.audit, tariff).items]
    return {
        "audit": _to_response(obj, result.audit),
        "snapshot": _snapshot_response(result.snapshot),
        "quality": asdict(result.quality),
        "sources": result.sources,
        "scope": asdict(scope),
        "regime": {
            key: getattr(regime, key)
            for key in (
                "p_in",
                "p_out",
                "p_bg",
                "q_day",
                "t",
                "w",
                "t_year",
            )
        },
        "losses": losses,
    }
