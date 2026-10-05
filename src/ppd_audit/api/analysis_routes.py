"""Выездной замер, кривые, мероприятия и требования к подключению."""

from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..config import load_constraints
from ..core.losses import build_loss_map
from ..services.analysis import (
    annual_summary,
    base_annual_injection,
    efficiency_assessment,
    measure_analysis,
    onboarding,
    working_point,
)
from ..services.audit import run_energy_audit
from ..services.forecast_data import injection_profile
from ..services.result_scope import result_scope
from ..services.telemetry_audit import object_from_database, run_snapshot_audit
from ..services.telemetry_quality import QualityIssue, TelemetryQuality
from ..spec import load_object_spec
from .analysis_contracts import AnalysisContext, MeasuresRequest
from .dashboard import _day_window, _require_ids


router = APIRouter()


def _database():
    from .main import _database as database

    return database()


def _context(database, object_id, aggregate_id, request):
    _require_ids(database, object_id, aggregate_id)
    if request.source == "field_trip":
        try:
            obj = load_object_spec(object_id)
            audit = run_energy_audit(obj, aggregate_id)
        except (KeyError, ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, detail=str(exc)) from exc
        rm = audit.spec.regime
        issues = []
        if audit.regime.eta_unit > 1:
            issues.append(
                QualityIssue(
                    "efficiency_above_one",
                    "КПД выше 1: гидравлическая мощность больше электрической.",
                    "error",
                )
            )
        scope = result_scope(rm, rm.t_year)
        if scope.annual_runtime_is_assumed:
            issues.append(
                QualityIssue(
                    "annual_runtime_assumed", "Годовая наработка принята равной 8760 ч.", "warning"
                )
            )
        quality = TelemetryQuality(
            "unfit"
            if any(i.severity == "error" for i in issues)
            else "assumptions"
            if issues
            else "ready",
            tuple(issues),
            {
                "pressure": "Выездной замер из YAML",
                "flow": "Выездной замер из YAML",
                "power": "Выездной замер из YAML",
            },
        )
        return obj, audit, scope, quality, {"YAML": obj.source or f"config/plants/{object_id}.yaml"}
    if not request.day or not request.timestamp:
        raise HTTPException(400, detail="для телеметрии требуются day и timestamp")
    start, end = _day_window(request.day)
    try:
        stamp = datetime.fromisoformat(request.timestamp)
        if stamp.tzinfo is not None:
            raise ValueError("телеметрия использует локальное время без UTC offset")
        if not start <= stamp < end:
            raise ValueError("снимок должен принадлежать выбранным суткам")
        result = run_snapshot_audit(
            database, object_id, aggregate_id, start, end, stamp, track_clarifications=False
        )
        obj = object_from_database(database, object_id, start, aggregate_code=aggregate_id)
        rm = result.audit.spec.regime
        return (
            obj,
            result.audit,
            result_scope(rm, None if result.annual_runtime_is_assumed else rm.t_year),
            result.quality,
            result.sources,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.post("/objects/{object_id}/aggregates/{aggregate_id}/field-trip-audit")
def field_trip_audit(object_id: str, aggregate_id: str):
    from .main import _to_response

    obj, audit, scope, quality, sources = _context(
        _database(), object_id, aggregate_id, AnalysisContext(source="field_trip")
    )
    tariff = load_constraints().economics.get("tariff_rub_kwh", 4.68)
    return {
        "audit": _to_response(obj, audit),
        "pump_assessment": efficiency_assessment(audit.regime.eta_unit, audit.regime.eta_nom),
        "source": "field_trip",
        "snapshot": None,
        "quality": asdict(quality),
        "scope": asdict(scope),
        "sources": sources,
        "regime": audit.spec.regime.model_dump(mode="json"),
        "passport": audit.spec.model_dump(mode="json", exclude={"regime", "reference"}),
        "losses": [asdict(v) for v in build_loss_map(audit, tariff).items]
        if quality.allows_economic_conclusions
        else [],
        "annual_summary": {
            key: value if quality.allows_economic_conclusions else None
            for key, value in annual_summary(audit, tariff).items()
        },
        "tariff": tariff,
        "target_sec": load_constraints().kpi.get("target_sec_2035"),
    }


@router.post("/objects/{object_id}/aggregates/{aggregate_id}/working-point")
def working_point_view(object_id: str, aggregate_id: str, request: AnalysisContext):
    _, audit, _, _, _ = _context(_database(), object_id, aggregate_id, request)
    return working_point(audit)


@router.post("/objects/{object_id}/aggregates/{aggregate_id}/measures")
def measures_view(object_id: str, aggregate_id: str, request: MeasuresRequest):
    database = _database()
    _, audit, scope, quality, _ = _context(database, object_id, aggregate_id, request)
    if not quality.allows_economic_conclusions:
        raise HTTPException(
            400,
            detail="Выбранный режим непригоден для экономических выводов: "
            + " ".join(i.message for i in quality.issues),
        )
    profile = (
        injection_profile(
            database,
            object_id,
            aggregate_id,
            base_annual_injection(audit, scope),
            horizon_years=request.horizon_years,
            period_days=request.period_days,
        )
        if request.basis == "forecast"
        else None
    )
    return measure_analysis(
        audit,
        scope,
        load_constraints().economics.get("tariff_rub_kwh", 4.68),
        profile,
        horizon_years=request.horizon_years,
        discount_rate=request.discount_rate,
        basis=request.basis,
        quality=quality,
    )


@router.get("/objects/{object_id}/aggregates/{aggregate_id}/onboarding")
def onboarding_view(object_id: str, aggregate_id: str, at: str | None = None):
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    try:
        if at is not None:
            start, _ = _day_window(at)
            obj = object_from_database(database, object_id, start, aggregate_code=aggregate_id)
        else:
            try:
                obj = load_object_spec(object_id)
            except FileNotFoundError:
                dates = database.telemetry_dates(object_id, aggregate_id)
                stamp = (
                    datetime.combine(dates[-1], datetime.min.time()) if dates else datetime.now()
                )
                obj = object_from_database(database, object_id, stamp, aggregate_code=aggregate_id)
        return onboarding(obj.aggregate(aggregate_id))
    except (KeyError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, detail=str(exc)) from exc
