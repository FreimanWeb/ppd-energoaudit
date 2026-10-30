"""Выездной замер, кривые, мероприятия и требования к подключению."""

from dataclasses import asdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

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
from ..services.armits_data import load_network, runtime_reading
from ..services.audit import run_energy_audit
from ..services.catalog import with_confirmed_density
from ..services.diagnostics import diagnose_aggregate
from ..services.forecast_data import injection_profile
from ..services.network_losses import build_network_analysis
from ..services.result_scope import result_scope
from ..services.telemetry_audit import object_from_database, run_snapshot_audit
from ..services.telemetry_quality import QualityIssue, TelemetryQuality
from ..spec import load_object_spec
from .analysis_contracts import AnalysisContext, MeasuresRequest, NetworkLossRequest
from .dashboard import _day_window, _require_ids, _tariff


router = APIRouter()


def _database():
    from .main import _database as database

    return database()


def _context(database, object_id, aggregate_id, request):
    _require_ids(database, object_id, aggregate_id)
    if request.source == "field_trip":
        try:
            obj = with_confirmed_density(load_object_spec(object_id), database)
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
        if rm.p_bg is not None and rm.p_bg > rm.p_out:
            issues.append(
                QualityIssue(
                    "bg_pressure_above_discharge",
                    "Давление БГ выше давления на выкиде: проверьте единицы и датчики.",
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
        sources = {"YAML": obj.source or f"config/plants/{object_id}.yaml"}
        density = database.plant_density_default(
            object_id, datetime.now(ZoneInfo("Europe/Moscow")).date()
        )
        if density:
            sources["ρ"] = density["source"]
        return obj, audit, scope, quality, sources
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

    database = _database()
    obj, audit, scope, quality, sources = _context(
        database, object_id, aggregate_id, AnalysisContext(source="field_trip")
    )
    tariff_selection = _tariff(database)
    tariff = tariff_selection["rub_per_kwh"]
    return {
        "audit": _to_response(obj, audit),
        "pump_assessment": efficiency_assessment(audit.regime.eta_unit, audit.regime.eta_nom),
        "diagnostics": asdict(diagnose_aggregate(object_id, audit, scope, quality)),
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
        "tariff_warning": tariff_selection["warning"],
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
    tariff_selection = _tariff(
        database, date.fromisoformat(request.day) if request.source == "telemetry" else None
    )
    result = measure_analysis(
        audit,
        scope,
        tariff_selection["rub_per_kwh"],
        profile,
        horizon_years=request.horizon_years,
        discount_rate=request.discount_rate,
        basis=request.basis,
        quality=quality,
    )
    result["tariff_warning"] = tariff_selection["warning"]
    return result


@router.get("/objects/{object_id}/aggregates/{aggregate_id}/onboarding")
def onboarding_view(
    object_id: str, aggregate_id: str, at: str | None = None, timestamp: str | None = None
):
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    try:
        if timestamp is not None:
            _, audit, _, _, _ = _context(
                database,
                object_id,
                aggregate_id,
                AnalysisContext(source="telemetry", day=at, timestamp=timestamp),
            )
            return {
                **onboarding(audit.spec),
                "basis": {"source": "telemetry", "day": at, "timestamp": timestamp},
            }
        if at is not None:
            start, _ = _day_window(at)
            obj = object_from_database(database, object_id, start, aggregate_code=aggregate_id)
            basis = {"source": "passport", "day": at, "timestamp": None}
        else:
            basis = {"source": "field_trip", "day": None, "timestamp": None}
            try:
                obj = with_confirmed_density(load_object_spec(object_id), database)
            except FileNotFoundError:
                dates = database.telemetry_dates(object_id, aggregate_id)
                stamp = (
                    datetime.combine(dates[-1], datetime.min.time()) if dates else datetime.now()
                )
                obj = object_from_database(database, object_id, stamp, aggregate_code=aggregate_id)
                basis = {"source": "passport", "day": stamp.date().isoformat(), "timestamp": None}
        return {**onboarding(obj.aggregate(aggregate_id)), "basis": basis}
    except (KeyError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.get("/objects/{object_id}/aggregates/{aggregate_id}/runtime-reading")
def aggregate_runtime_reading(object_id: str, aggregate_id: str):
    _require_ids(_database(), object_id, aggregate_id)
    return {"reading": runtime_reading(object_id, aggregate_id)}


@router.post("/objects/{object_id}/aggregates/{aggregate_id}/network-losses")
def network_losses_view(object_id: str, aggregate_id: str, request: NetworkLossRequest):
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    network = load_network(object_id)
    if network is None:
        return {
            "status": "unavailable",
            "measures": [],
            "comparison": None,
            "warnings": ["Сеть АРМИТС пока подключена только для КНС-54."],
        }
    _, audit, _, quality, sources = _context(database, object_id, aggregate_id, request)
    if quality.status == "unfit":
        return {
            "status": "unavailable",
            "measures": [],
            "comparison": None,
            "warnings": ["Выбранный режим непригоден для построения энергетического баланса."]
            + [issue.message for issue in quality.issues],
        }
    try:
        result = build_network_analysis(
            audit, network, request.scenario.model_dump(), request.intervention
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    result["runtime_reading"] = runtime_reading(object_id, aggregate_id)
    result["context"] = request.model_dump(exclude={"scenario"})
    result["sources"] = sources
    result["warnings"] = list(
        dict.fromkeys([issue.message for issue in quality.issues] + result.get("warnings", []))
    )
    return result


@router.get("/objects/{object_id}/wells")
def object_wells(object_id: str):
    database = _database()
    _require_ids(database, object_id)
    return {
        "wells": database.wells(object_id),
        "density_default": database.plant_density_default(
            object_id, datetime.now(ZoneInfo("Europe/Moscow")).date()
        ),
    }


@router.get("/objects/{object_id}/wells/{well_code}/history")
def well_history(object_id: str, well_code: str):
    database = _database()
    _require_ids(database, object_id)
    records = database.well_history(object_id, well_code)
    if not records:
        raise HTTPException(404, detail="История скважины не найдена")
    from ..services.demo import DEMO_OBJECT_ID

    return {
        "well_code": well_code,
        "records": records,
        "warnings": [
            "Демонстрационные данные: давления, закачка и ГДИ синтетические; "
            "не являются результатами измерений.",
        ]
        if object_id == DEMO_OBJECT_ID
        else [
            "Давления сохранены в исходных «атм». Перевод в МПа требует подтверждения единиц.",
            "Дата текущего режима — дата выгрузки, фактическая дата измерения не подтверждена.",
            "Нулевые значения и повторяющиеся записи сохранены с источниками; "
            "ноль может означать отсутствие измерения.",
            "Месяц выгрузки может быть неполным. "
            "Месячные записи не являются двухчасовой телеметрией.",
            "Давления и плотности ГДИ относятся к скважине и исследованию, а не к насосу станции.",
        ],
    }
