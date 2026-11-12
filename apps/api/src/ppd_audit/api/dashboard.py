"""Чтение данных для React-frontend через HTTP API."""

from dataclasses import asdict
from datetime import date, datetime, time, timedelta

import yaml
from fastapi import APIRouter, HTTPException

from ..config import load_constraints, project_root
from ..core.losses import build_loss_map
from ..db import AuditDatabase
from ..services import catalog, telemetry_view
from ..services.analysis import annual_summary, efficiency_assessment
from ..services.diagnostics import diagnose_aggregate
from ..services.result_scope import result_scope
from ..services.scheme_data import scheme_pressures
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


def _tariff(database: AuditDatabase, at: date | None = None) -> dict:
    try:
        return catalog.tariff(at, database=database)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


def _day_window(day: str) -> tuple[datetime, datetime]:
    try:
        parsed = date.fromisoformat(day)
        if parsed.isoformat() != day:
            raise ValueError("дата должна иметь формат YYYY-MM-DD")
        if parsed == date.max:
            raise ValueError("конец суток выходит за допустимый диапазон")
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
        "power_age_seconds": snapshot.power_age.total_seconds() if snapshot.power_age else 0,
        "p_bg_age_seconds": snapshot.p_bg_age.total_seconds()
        if snapshot.p_bg_age is not None
        else None,
    }


@router.get("/objects/{object_id}/aggregates", response_model=list[AggregateSummary])
def aggregates(object_id: str) -> list[dict]:
    database = _database()
    _require_ids(database, object_id)
    return catalog.aggregate_index(database, object_id)


@router.get(
    "/objects/{object_id}/aggregates/{aggregate_id}/dates",
    response_model=TelemetryDates,
)
def dates(object_id: str, aggregate_id: str) -> dict:
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    days = database.telemetry_dates(object_id, aggregate_id)
    default = telemetry_view.last_usable_day(database, object_id, aggregate_id)
    default = default or database.last_day_with_daily_totals(object_id, aggregate_id)
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


@router.get("/objects/{object_id}/scheme-pressures")
def branch_pressures(object_id: str, day: str, timestamp: str) -> dict[str, dict[str, float]]:
    database = _database()
    _require_ids(database, object_id)
    start, end = _day_window(day)
    try:
        selected = datetime.fromisoformat(timestamp)
        if selected.tzinfo is not None:
            raise ValueError("телеметрия использует локальное время без UTC offset")
        if not start <= selected < end:
            raise ValueError("снимок должен принадлежать выбранным суткам")
        return scheme_pressures(database, object_id, selected)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.get("/objects/{object_id}/topology", response_model=TopologyResponse)
def topology(object_id: str) -> dict:
    database = _database()
    plant = _require_ids(database, object_id)
    path = project_root() / "config" / "topology" / f"{object_id}.yaml"
    aggregate_codes = {item["code"] for item in database.aggregates(object_id)}
    if path.exists():
        graph = yaml.safe_load(path.read_text(encoding="utf-8"))
        for node in graph["nodes"]:
            if node["type"] == "pump" and not node.get("agg"):
                if node["label"] in aggregate_codes:
                    node["agg"] = node["label"]
        return {**graph, "is_typical": False}

    nodes, edges = [], []
    aggregate_list = aggregates(object_id)
    groups: dict[str, list[tuple[int, dict]]] = {}
    for index, aggregate in enumerate(aggregate_list):
        groups.setdefault(aggregate["technical_place_code"], []).append((index, aggregate))
    cursor = (len(aggregate_list) - 1) / 2
    multiple = len(groups) > 1
    for code, members in groups.items():
        suffix = f"-{code}" if multiple else ""
        group_name = members[0][1]["technical_place_name"] if multiple else None
        center = cursor - (len(members) - 1) / 2
        nodes.append({
            "id": f"src{suffix}",
            "type": "source",
            "x": 0,
            "y": center,
            "label": "Приём воды",
            "sub": group_name,
        })
        for row, (index, aggregate) in enumerate(members):
            node_id = f"pump-{index}"
            nodes.append({
                "id": node_id,
                "type": "pump",
                "x": 1,
                "y": cursor - row,
                "label": aggregate["code"],
                "agg": aggregate["code"],
                "sub": aggregate["pump_model"],
            })
            edges.extend([
                {"from": f"src{suffix}", "to": node_id},
                {"from": node_id, "to": f"comb{suffix}"},
            ])
        for index, (node_id, kind, label) in enumerate(
            [
                ("comb", "manifold", "Блок гребёнок"),
                ("valve", "valve", "ЗРА / штуцеры"),
                ("wells", "wells", "Нагнетательные скважины"),
                ("res", "reservoir", "Пласт / призабойная зона"),
            ],
            start=2,
        ):
            nodes.append({
                "id": f"{node_id}{suffix}",
                "type": kind,
                "x": index,
                "y": center,
                "label": label,
                "sub": group_name,
            })
        edges.extend([
            {"from": f"comb{suffix}", "to": f"valve{suffix}"},
            {"from": f"valve{suffix}", "to": f"wells{suffix}", "kind": "throttle"},
            {"from": f"wells{suffix}", "to": f"res{suffix}"},
        ])
        cursor -= len(members) + 1
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
    if request.measurement_id is not None:
        raise HTTPException(400, detail="measurement_id допустим только для source=field_trip")
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
            equipment_override=request.equipment_override,
        )
        obj = object_from_database(
            database,
            object_id,
            timestamp,
            aggregate_code=aggregate_id,
            equipment_override=request.equipment_override,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    regime = result.audit.spec.regime
    scope = result_scope(
        result.audit,
        daily_pressure_coverage_is_complete=False,
    )
    constraints = load_constraints()
    tariff_selection = _tariff(database, start.date())
    tariff = tariff_selection["rub_per_kwh"]
    losses = []
    if result.quality.allows_economic_conclusions:
        losses = [asdict(item) for item in build_loss_map(result.audit, tariff).items]
    return {
        "audit": _to_response(obj, result.audit),
        "pump_assessment": efficiency_assessment(
            result.audit.regime.eta_unit, result.audit.regime.eta_nom
        ),
        "snapshot": _snapshot_response(result.snapshot),
        "quality": asdict(result.quality),
        "sources": result.sources,
        "scope": asdict(scope),
        "diagnostics": asdict(diagnose_aggregate(object_id, result.audit, scope, result.quality)),
        "regime": regime.model_dump(mode="json"),
        "losses": losses,
        "source": "telemetry",
        "passport": result.audit.spec.model_dump(mode="json", exclude={"regime", "reference"}),
        "annual_summary": {
            key: value if result.quality.allows_economic_conclusions else None
            for key, value in annual_summary(result.audit, tariff).items()
        },
        "tariff": tariff,
        "tariff_warning": tariff_selection["warning"],
        "target_sec": constraints.kpi.get("target_sec_2035"),
        "analysis_context": {
            "source": "telemetry",
            "day": request.day,
            "timestamp": request.timestamp,
            "measurement_id": None,
            "equipment_override": request.equipment_override.model_dump(mode="json")
            if request.equipment_override is not None
            else None,
        },
    }
