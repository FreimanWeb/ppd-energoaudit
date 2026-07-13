"""FastAPI entrypoint for production integration."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from ..core.audit import AuditResult
from ..services.audit import run_energy_audit
from ..spec import ObjectSpec
from ..telemetry import (
    TelemetrySubmission,
    TelemetryValidationResponse,
    map_telemetry_to_calculation_input,
    validate_telemetry,
)
from .contracts import EnergyAuditMetrics, EnergyAuditRequest, EnergyAuditResponse


app = FastAPI(title="PPD Energoaudit API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
        trace=result.trace,
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
