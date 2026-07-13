"""HTTP API contracts.

Core models stay in ``spec.py``; these DTOs freeze the API shape without
duplicating the plant passport schema.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..spec import ObjectSpec


class EnergyAuditRequest(BaseModel):
    object: ObjectSpec = Field(..., description="Нормализованный паспорт и режим объекта")
    aggregate_id: str | None = Field(None, description="Агрегат; по умолчанию первый рабочий")


class EnergyAuditMetrics(BaseModel):
    flow_m3h: float
    h_fact_m: float
    p_hydraulic_kw: float
    p_electric_kw: float
    eta_unit: float
    eta_nom: float
    load_factor: float
    eta_motor_real: float
    eta_pump: float
    sec_fact_kwh_m3: float
    sec_calc_kwh_m3: float
    dw_efficiency_kwh_year: float
    h_due_m: float | None = None
    sec_optimal_kwh_m3: float | None = None
    dw_throttle_kwh_year: float | None = None


class EnergyAuditResponse(BaseModel):
    object_id: str
    object_name: str
    aggregate_id: str
    branch: str
    pump_kind: str
    metrics: EnergyAuditMetrics
    trace: dict[str, dict]
