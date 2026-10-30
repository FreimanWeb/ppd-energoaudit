"""JSON contracts телеметрии, прогнозов и внешних CRM-выгрузок."""

from typing import Any

from pydantic import BaseModel


class SeriesPoint(BaseModel):
    timestamp: str
    value: float


class TelemetrySeries(BaseModel):
    metric: str
    unit: str
    points: list[SeriesPoint]


class TelemetryResponse(BaseModel):
    records: list[dict[str, Any]]
    series: list[TelemetrySeries]


class CalendarResponse(BaseModel):
    statuses: dict[str, str]


class HistoryPoint(BaseModel):
    period: int
    value: float
    period_start: str | None = None
    period_end: str | None = None


class ForecastPoint(HistoryPoint):
    lower: float
    upper: float


class ForecastResponse(BaseModel):
    history: list[HistoryPoint]
    forecast: list[ForecastPoint]
    trend_slope: float | None
    naive_baseline: float | None
    method: str
    estimate: bool
    note: str
    period_days: int
    unused_daily_count: int = 0
    missing_daily_count: int = 0


class CrmRun(BaseModel):
    code: str
    title: str
    events: bool
    object_id: str | None
    model: str | None


class SourceError(BaseModel):
    error: str


class CrmDailyForecast(BaseModel):
    interval_hours: float
    by_unit: dict[str, list[tuple[str, float]]]
    total: list[tuple[str, float]]
    partial_days: list[str]
    model: str | None
    events: bool


class WellRun(BaseModel):
    code: str
    title: str
    mode: str | None


class WellMonthTotal(BaseModel):
    month: str
    base: float
    forecast: float
    fact: float | None


class WellForecastRow(BaseModel):
    well_key: str
    month: str
    well: str
    base: float | None
    forecast: float | None
    fact: float | None
    deviation: float | None
    share: float | None
    r_ust: float | None
    r_ust_fact: float | None


class WellReport(BaseModel):
    months: list[str]
    wells: list[str]
    has_fact: bool
    totals: list[WellMonthTotal]
    rows: list[WellForecastRow]


class WellEdge(BaseModel):
    source: str
    target: str
    strength: float


class WellNeighbour(BaseModel):
    target: str
    strength: float


class WellCentrality(BaseModel):
    well: str
    strength_sum: float
    degree: float
    betweenness: float
    top_neighbor: str | None
    top_neighbor_strength: float | None


class WellGraph(BaseModel):
    positions: dict[str, tuple[float, float]]
    edges: list[WellEdge]
    by_well: dict[str, list[WellNeighbour]]
    centrality: list[WellCentrality]


class WellDowntime(BaseModel):
    well_key: str
    well: str
    reason: str
    since: str | None
    runtime_hours: float | None


class Clarification(BaseModel):
    field: str
    provisional_value: str
    reason: str


class CrmFactSeries(BaseModel):
    aggregate: str
    points: list[tuple[str, float]]


class CrmFactResponse(BaseModel):
    series: list[CrmFactSeries]


class WellMonthlyView(BaseModel):
    series: list[WellMonthTotal]
    downtime_marks: list[WellDowntime]
    window: tuple[str, str] | None
    last: WellMonthTotal | None


class NetworkWell(BaseModel):
    well: str
    q_m3h: float
    annual_volume_m3: float
    path_length_m: float
    path_complete: bool
    has_geometry: bool
    path_pipeline_names: list[str]
    p_before_choke_mpa: float | None
    p_after_choke_mpa: float | None
    dp_network_mpa: float | None
    dp_friction_mpa: float
    dp_other_mpa: float | None
    dp_choke_mpa: float | None
    friction_kw: float
    other_kw: float
    choke_kw: float
    loss_kw: float
    annual_kwh: float
    consistent: bool
    flags: list[str]


class NetworkPipeline(BaseModel):
    name: str
    start: str
    end: str
    length_m: float
    sizes: str
    inner_mm: float
    pipe_types: str
    q_m3h: float
    velocity_ms: float
    dp_friction_mpa: float


class NetworkTotals(BaseModel):
    q_m3h: float
    friction_kw: float
    other_kw: float
    choke_kw: float
    friction_kwh: float
    other_kwh: float
    choke_kwh: float
    total_kwh: float
    money_krub: float
    required_pressure_mpa: float | None
    excess_pressure_mpa: float | None
    excess_kwh: float


class NetworkCoverage(BaseModel):
    cards: int
    wells: int
    complete_paths: int
    partial_paths: int
    no_geometry: int
    inconsistent: int


class ManifoldSource(BaseModel):
    kind: str
    start: str | None
    end: str | None


class NetworkFluid(BaseModel):
    rho: float
    nu_cst: float
    temperature_c: float


class NetworkView(BaseModel):
    object_id: str
    month: str | None
    p_bg_mpa: float
    p_bg_source: ManifoldSource
    fluid: NetworkFluid
    eta: float
    eta_basis: str
    tariff: float
    totals: NetworkTotals
    coverage: NetworkCoverage
    wells: list[NetworkWell]
    pipelines: list[NetworkPipeline]
