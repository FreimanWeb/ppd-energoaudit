"""HTTP API contracts.

Core models stay in ``spec.py``; these DTOs freeze the API shape without
duplicating the plant passport schema.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..services.diagnostics import DiagnosticReport
from ..spec import EquipmentData, ObjectSpec


class EnergyAuditRequest(BaseModel):
    object: ObjectSpec = Field(..., description="Нормализованный паспорт и режим объекта")
    aggregate_id: str | None = Field(None, description="Агрегат; по умолчанию первый рабочий")


class EnergyAuditMetrics(BaseModel):
    flow_m3h: float
    h_fact_m: float
    p_hydraulic_kw: float
    p_electric_kw: float
    eta_unit: float
    eta_nom: float | None
    load_factor: float | None
    eta_motor_real: float | None
    eta_pump: float | None
    sec_fact_kwh_m3: float
    sec_calc_kwh_m3: float | None
    dw_efficiency_kwh_year: float | None
    h_due_m: float | None = None
    sec_optimal_kwh_m3: float | None = None
    dw_throttle_kwh_year: float | None = None
    power_operating_avg_kw: float | None = None
    power_daily_avg_kw: float | None = None
    power_daily_reported_kw: float | None = None


class EnergyAuditResponse(BaseModel):
    object_id: str
    object_name: str
    aggregate_id: str
    branch: str
    pump_kind: str
    metrics: EnergyAuditMetrics
    trace: dict[str, dict]


class PlantSummary(BaseModel):
    code: str
    name: str
    ngdu_name: str
    water_type: str
    branch: str
    is_example: bool


class CatalogPlantSummary(PlantSummary):
    has_telemetry: bool
    has_network: bool = False


class TelemetryStored(BaseModel):
    stored: int


class TelemetryAuditWindow(BaseModel):
    start: datetime
    end: datetime


class AggregateSummary(BaseModel):
    code: str
    role: str
    pump_model: str | None = None
    has_telemetry: bool
    technical_place_code: str = "main"
    technical_place_name: str = "Основная группа"


class TelemetryDates(BaseModel):
    dates: list[str]
    default_date: str | None = None


class SnapshotResponse(BaseModel):
    timestamp: str
    p_in_mpa: float
    p_out_mpa: float
    p_bg_mpa: float | None
    power_kw: float
    power_age_seconds: float | None = None
    p_bg_age_seconds: float | None = None


class TopologyNode(BaseModel):
    id: str
    type: str
    x: float
    y: float
    label: str
    sub: str | None = None
    agg: str | None = None
    hint: str | None = None


class TopologyEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    kind: str | None = None


class TopologyResponse(BaseModel):
    title: str
    source: str
    is_typical: bool
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


class SnapshotAuditRequest(BaseModel):
    day: str
    timestamp: str
    measurement_id: int | None = None
    equipment_override: EquipmentData | None = None


class QualityIssueResponse(BaseModel):
    code: str
    message: str
    severity: Literal["warning", "error"]


class QualityResponse(BaseModel):
    status: Literal["ready", "assumptions", "unfit"]
    issues: list[QualityIssueResponse]
    basis: dict[str, str]


class ResultScopeResponse(BaseModel):
    annual_runtime_hours: float
    annual_runtime_is_assumed: bool
    daily_kpi_is_fact: bool


class RegimeResponse(BaseModel):
    measured_at: date | None = None
    p_in: float
    p_out: float
    p_bg: float | None
    q_day: float | None
    t: float | None
    w: float | None
    t_year: float | None
    rho: float = 1000
    q_fact: float | None = None
    p_electric: float | None = None
    power_daily_reported: float | None = None
    nu: float | None = None


class LossResponse(BaseModel):
    name: str
    power_kw: float
    share: float
    annual_kwh: float | None
    annual_rub: float | None
    category: str


class SnapshotAuditResponse(BaseModel):
    pump_assessment: dict[str, str]
    diagnostics: DiagnosticReport
    audit: EnergyAuditResponse
    snapshot: SnapshotResponse
    quality: QualityResponse
    sources: dict[str, str]
    scope: ResultScopeResponse
    regime: RegimeResponse
    losses: list[LossResponse]
    source: Literal["telemetry", "field_trip"] = "telemetry"
    passport: dict = Field(default_factory=dict)
    annual_summary: dict[str, float | None] = Field(default_factory=dict)
    tariff: float = 4.68
    tariff_warning: str | None = None
    target_sec: float | None = None
    analysis_context: dict | None = None
