"""FastAPI entrypoint for production integration."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status

from ..config import project_root
from ..core.audit import AuditResult
from ..db import AuditDatabase, default_database_path
from ..db_seed import bootstrap_database
from ..services import catalog
from ..services.audit import run_energy_audit
from ..services.formula_view import formula_entries
from ..services.telemetry_audit import run_telemetry_audit
from ..spec import ObjectSpec
from ..telemetry import (
    TelemetrySubmission,
    TelemetryValidationResponse,
    map_telemetry_to_calculation_input,
    validate_telemetry,
)
from .analysis_routes import router as analysis_router
from .auth_routes import AuthenticationMiddleware, router as auth_router
from .contracts import (
    CatalogPlantSummary,
    EnergyAuditMetrics,
    EnergyAuditRequest,
    EnergyAuditResponse,
    PlantSummary,
    TelemetryAuditWindow,
    TelemetryStored,
)
from .dashboard import router as dashboard_router
from .data_routes import router as data_router
from .monitoring_routes import router as monitoring_router
from .station_routes import router as station_router


@asynccontextmanager
async def _lifespan(_: FastAPI):
    """Подготовить БД до первого запроса: справочники и выгрузки АСУ ТП.

    Если БД уже собрана (``python -m ppd_audit.build_db``), это проверка
    набора файлов и выход; иначе импорт занимает около минуты.
    """
    if os.getenv("PPD_SKIP_DATA_PREPARE") != "1":
        path = Path(os.getenv("PPD_DATABASE_PATH", default_database_path()))
        root = Path(__file__).resolve().parents[3]
        await asyncio.to_thread(catalog.prepare_database, root, path)
    yield


app = FastAPI(title="PPD Energoaudit API", version="0.1.0", lifespan=_lifespan)
app.include_router(dashboard_router)
app.include_router(data_router)
app.include_router(monitoring_router)
app.include_router(analysis_router)
app.include_router(station_router)
app.include_router(auth_router)
app.add_middleware(AuthenticationMiddleware)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _database() -> AuditDatabase:
    path = Path(os.getenv("PPD_DATABASE_PATH", default_database_path()))
    return bootstrap_database(path, project_root() / "config" / "plants", include_demo=True)


@app.get("/objects", response_model=list[PlantSummary])
def list_objects() -> list[dict]:
    return _database().plants()


@app.get("/catalog/objects", response_model=list[CatalogPlantSummary])
def list_catalog_objects() -> list[dict]:
    return [
        {
            "code": item["id"],
            "name": item["name"],
            "ngdu_name": item["ngdu"],
            "water_type": item["water"],
            "branch": item["branch"],
            "is_example": item["id"] == "demo-ppd",
            "has_telemetry": item["has_telemetry"],
        }
        for item in catalog.object_index(_database())
    ]


def _to_response(spec: ObjectSpec, result: AuditResult) -> EnergyAuditResponse:
    regime = result.regime
    return EnergyAuditResponse(
        object_id=spec.id,
        object_name=spec.name,
        aggregate_id=result.aggregate_id,
        branch=result.branch,
        pump_kind=result.pump_kind,
        metrics=EnergyAuditMetrics(
            flow_m3h=regime.q,
            h_fact_m=regime.h_fact,
            p_hydraulic_kw=regime.p_hydraulic,
            p_electric_kw=regime.p_electric,
            eta_unit=regime.eta_unit,
            eta_nom=regime.eta_nom,
            load_factor=result.load_factor,
            eta_motor_real=result.eta_motor_real,
            eta_pump=result.eta_pump,
            sec_fact_kwh_m3=result.sec_fact,
            sec_calc_kwh_m3=result.sec_calc,
            dw_efficiency_kwh_year=result.dw_efficiency,
            h_due_m=result.h_due,
            sec_optimal_kwh_m3=result.sec_optimal,
            dw_throttle_kwh_year=result.dw_throttle,
        ),
        trace=formula_entries(result.trace),
    )


@app.post("/energy/audit", response_model=EnergyAuditResponse)
def create_energy_audit(request: EnergyAuditRequest) -> EnergyAuditResponse:
    try:
        result = run_energy_audit(request.object, request.aggregate_id)
        return _to_response(request.object, result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/objects/{object_id}/aggregates/{aggregate_id}/audits",
    response_model=EnergyAuditResponse,
)
def telemetry_energy_audit(
    object_id: str, aggregate_id: str, window: TelemetryAuditWindow
) -> EnergyAuditResponse:
    if window.end <= window.start:
        raise HTTPException(status_code=400, detail="конец окна должен быть позже начала")
    database = _database()
    try:
        result = run_telemetry_audit(database, object_id, aggregate_id, window.start, window.end)
        plant = database.plant(object_id)
        return _to_response(ObjectSpec(id=object_id, name=plant["name"]), result)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/telemetry/validate", response_model=TelemetryValidationResponse)
def validate_telemetry_submission(submission: TelemetrySubmission) -> TelemetryValidationResponse:
    payload = submission.to_payload()
    aggregate_ids = sorted({record.aggregate_id for record in submission.records})
    return TelemetryValidationResponse(
        validation=validate_telemetry(payload),
        normalized_by_aggregate={
            aggregate_id: map_telemetry_to_calculation_input(payload, aggregate_id)
            for aggregate_id in aggregate_ids
        },
    )


@app.post("/telemetry", response_model=TelemetryStored, status_code=status.HTTP_201_CREATED)
def store_telemetry_submission(submission: TelemetrySubmission) -> TelemetryStored:
    database = _database()
    try:
        for record in submission.records:
            metric, unit = _database_metric(record.metric.value)
            database.add_measurement(
                submission.object_id,
                record.aggregate_id,
                record.timestamp,
                metric,
                record.value,
                unit,
                technical_place_code=submission.technical_place,
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TelemetryStored(stored=len(submission.records))


def _database_metric(metric: str) -> tuple[str, str]:
    mappings = {
        "p_in": ("p_in", "МПа"),
        "p_out": ("p_out", "МПа"),
        "p_bg": ("p_bg", "МПа"),
        "flow_rate": ("flow_rate", "м³/ч"),
        "q_day": ("q_day", "м³/сут"),
        "runtime": ("runtime", "ч"),
        "energy": ("energy", "кВт·ч"),
        "power": ("power", "кВт"),
        "density": ("density", "кг/м³"),
        "viscosity": ("viscosity", "сСт"),
        "level": ("level", "мм"),
        "pump_state": ("pump_state", ""),
    }
    try:
        return mappings[metric]
    except KeyError as exc:
        raise ValueError(f"неподдерживаемая telemetry metric: {metric}") from exc
