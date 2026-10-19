"""HTTP data routes для нового frontend без Streamlit-зависимостей."""

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..db import AuditDatabase
from ..services import catalog, crm_view, forecast_data, network_view, telemetry_view
from ..services.telemetry_audit import telemetry_date_statuses
from ..services.telemetry_series import reduce_pressure_points, telemetry_series
from .data_contracts import (
    CalendarResponse,
    Clarification,
    CrmDailyForecast,
    CrmFactResponse,
    CrmRun,
    ForecastResponse,
    NetworkView,
    SourceError,
    TelemetryResponse,
    WellDowntime,
    WellGraph,
    WellMonthlyView,
    WellReport,
    WellRun,
)


_ROOT = Path(__file__).resolve().parents[3]
CRM_DIR = catalog.source_paths(_ROOT)["crm"]
SCADA_TAGS = catalog.source_paths(_ROOT)["scada_tags"]
DOWNTIME_DIR = catalog.source_paths(_ROOT)["downtime"]
NETWORK_DIR = catalog.source_paths(_ROOT)["network"]
NETWORK_CONFIG = catalog.source_paths(_ROOT)["network_config"]
router = APIRouter()


def _database() -> AuditDatabase:
    from .main import _database as database

    return database()


def _require_ids(database: AuditDatabase, object_id: str, aggregate_id: str | None = None):
    try:
        database.plant(object_id)
        if aggregate_id is not None:
            database.aggregate(object_id, aggregate_id)
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc


def _period(start: str, end: str) -> tuple[date, date]:
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first.isoformat() != start or last.isoformat() != end:
            raise ValueError("даты должны иметь формат YYYY-MM-DD")
        if last == date.max:
            raise ValueError("конец периода должен быть раньше 9999-12-31")
        if last < first:
            raise ValueError("конец периода должен быть не раньше начала")
        if (last - first).days > 3660:
            raise ValueError("период не должен превышать 10 лет")
        return first, last
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.get("/objects/{object_id}/telemetry", response_model=TelemetryResponse)
def telemetry(object_id: str, aggregate_id: str, start: str, end: str) -> dict:
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    first, last = _period(start, end)
    rows = telemetry_view.telemetry_for_period(database, object_id, aggregate_id, first, last)
    series = telemetry_series(
        rows,
        start=datetime.combine(first, time.min),
        end=datetime.combine(last + timedelta(days=1), time.min),
    )
    series = {
        unit: reduce_pressure_points(frame) if unit == "МПа" else frame
        for unit, frame in series.items()
    }
    return {
        "records": rows,
        "series": [
            {
                "metric": label,
                "unit": unit,
                "points": [
                    {"timestamp": row["Время"].isoformat(), "value": row["Значение"]}
                    for _, row in points.iterrows()
                ],
            }
            for unit, frame in series.items()
            for label, points in frame.groupby("Показатель", sort=False)
        ],
    }


@router.get(
    "/objects/{object_id}/aggregates/{aggregate_id}/calendar", response_model=CalendarResponse
)
def calendar(object_id: str, aggregate_id: str, month: str) -> dict:
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    try:
        first = date.fromisoformat(month + "-01")
        if first.strftime("%Y-%m") != month:
            raise ValueError("неверный формат месяца")
    except ValueError as exc:
        raise HTTPException(400, detail="месяц должен иметь формат YYYY-MM") from exc
    days = [
        day
        for day in database.telemetry_dates(object_id, aggregate_id)
        if day.year == first.year and day.month == first.month
    ]
    statuses = telemetry_date_statuses(database, object_id, aggregate_id, days)
    return {"statuses": {day.isoformat(): status for day, status in statuses.items()}}


@router.get(
    "/objects/{object_id}/aggregates/{aggregate_id}/forecast", response_model=ForecastResponse
)
def forecast(
    object_id: str,
    aggregate_id: str,
    start: str,
    end: str,
    period_days: Annotated[int, Query(ge=1, le=30, json_schema_extra={"enum": [1, 7, 30]})] = 30,
    horizon: Annotated[int, Query(ge=1, le=3660)] = 36,
) -> dict:
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    first, last = _period(start, end)
    if period_days not in (1, 7, 30):
        raise HTTPException(400, detail="period_days должен быть 1, 7 или 30")
    try:
        return forecast_data.forecast_series(
            database,
            object_id,
            aggregate_id,
            first,
            last,
            period_days=period_days,
            horizon=horizon,
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.get("/objects/{object_id}/crm/runs", response_model=list[CrmRun])
def crm_runs(object_id: str) -> list[dict]:
    _require_ids(_database(), object_id)
    return crm_view.crm_runs(CRM_DIR, object_id)


@router.get(
    "/objects/{object_id}/crm/runs/{run_code}", response_model=CrmDailyForecast | SourceError
)
def crm_daily_forecast(object_id: str, run_code: str) -> dict:
    _require_ids(_database(), object_id)
    result = crm_view.crm_daily_forecast(CRM_DIR, SCADA_TAGS, object_id, run_code)
    if result is None:
        raise HTTPException(404, detail="прогон CRM не найден")
    return result


@router.get("/objects/{object_id}/crm/well-runs", response_model=list[WellRun])
def crm_well_runs(object_id: str) -> list[dict]:
    _require_ids(_database(), object_id)
    return crm_view.crm_well_runs(CRM_DIR, object_id)


@router.get(
    "/objects/{object_id}/crm/well-runs/{run_code}", response_model=WellReport | SourceError
)
def crm_wells_report(object_id: str, run_code: str) -> dict:
    _require_ids(_database(), object_id)
    result = crm_view.crm_wells_report(CRM_DIR, object_id, run_code)
    if result is None:
        raise HTTPException(404, detail="прогон CRM по скважинам не найден")
    return result


@router.get(
    "/objects/{object_id}/crm/well-runs/{run_code}/graph",
    response_model=WellGraph | SourceError,
)
def crm_wells_graph(
    object_id: str,
    run_code: str,
    edge_limit: Annotated[int, Query(ge=1, le=1000)] = 60,
) -> dict:
    _require_ids(_database(), object_id)
    result = crm_view.crm_wells_graph(CRM_DIR, object_id, run_code, edge_limit)
    if result is None:
        raise HTTPException(404, detail="прогон CRM по скважинам не найден")
    return result


@router.get("/objects/{object_id}/well-downtime", response_model=list[WellDowntime])
def well_downtime(object_id: str) -> list[dict]:
    _require_ids(_database(), object_id)
    return crm_view.well_downtime(DOWNTIME_DIR, object_id)


@router.get("/objects/{object_id}/clarifications", response_model=list[Clarification])
def clarifications(object_id: str, aggregate_id: str) -> list[dict]:
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    return catalog.open_clarifications(database, object_id, aggregate_id)


@router.get("/objects/{object_id}/crm/fact", response_model=CrmFactResponse)
def crm_fact(object_id: str, aggregates: str, start: str, end: str) -> dict:
    database = _database()
    _require_ids(database, object_id)
    first, last = _period(start, end)
    codes = list(dict.fromkeys(code.strip() for code in aggregates.split(",") if code.strip()))
    if not codes or len(codes) > 50:
        raise HTTPException(400, detail="нужно от 1 до 50 агрегатов")
    for code in codes:
        _require_ids(database, object_id, code)
    return {
        "series": [
            {
                "aggregate": code,
                "points": telemetry_view.daily_injection_series(
                    database, object_id, code, first, last
                ),
            }
            for code in codes
        ]
    }


@router.get(
    "/objects/{object_id}/crm/well-runs/{run_code}/monthly",
    response_model=WellMonthlyView | SourceError,
)
def crm_monthly_view(object_id: str, run_code: str, well: str | None = None) -> dict:
    _require_ids(_database(), object_id)
    report = crm_view.crm_wells_report(CRM_DIR, object_id, run_code)
    if report is None:
        raise HTTPException(404, detail="прогон CRM по скважинам не найден")
    if "error" in report:
        return report
    downtime = crm_view.well_downtime(DOWNTIME_DIR, object_id)
    return crm_view.monthly_view(report, downtime, well)


@router.get("/objects/{object_id}/network", response_model=NetworkView | SourceError)
def network(
    object_id: str,
    eta: Annotated[float | None, Query(gt=0, le=1)] = None,
) -> dict:
    """Разводящая сеть: трение в водоводах, прочие потери и штуцеры по скважинам.

    ``eta`` — КПД насосной установки для годовой энергии; без него берётся
    номинальный КПД агрегатов станции.
    """
    database = _database()
    _require_ids(database, object_id)
    return network_view.network_view(
        database, NETWORK_DIR, NETWORK_CONFIG, object_id,
        tariff=catalog.tariff(database=database)["rub_per_kwh"], eta=eta,
    )
