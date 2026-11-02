"""Входы расчётных представлений: единый выбор источника режима."""

from typing import Literal

from pydantic import BaseModel, Field

from ..spec import EquipmentData


class AnalysisContext(BaseModel):
    """Выбор режима для всех расчётных представлений одним контрактом.

    measurement_id — ручной замер из /manual-measurements, допустим только с
    source="field_trip". equipment_override — временный сценарий оборудования:
    применяется к расчёту на запрос, нигде не сохраняется и не подтверждает
    кривые (curve_source.verified принудительно снимается).
    """

    source: Literal["telemetry", "field_trip"] = "telemetry"
    day: str | None = None
    timestamp: str | None = None
    measurement_id: int | None = None
    equipment_override: EquipmentData | None = None


class MeasuresRequest(AnalysisContext):
    horizon_years: int = Field(3, ge=1, le=10)
    discount_rate: float = Field(0.15, ge=0, le=0.6)
    period_days: int = Field(30, ge=1, le=365)
    basis: Literal["annual", "forecast"] = "annual"


class NetworkLossScenario(BaseModel):
    """Синтетические параметры; давления заданы как поверхностный эквивалент."""

    model_config = {"extra": "forbid", "allow_inf_nan": False}

    roughness_mm: float = Field(0.1, ge=0, le=5)
    well_depth_m: float = Field(1800, ge=1, le=10000)
    well_diameter_mm: float = Field(62, ge=10, le=500)
    local_resistance_k: float = Field(2, ge=0, le=1000)
    useful_pressure_mpa: float = Field(3, ge=0, le=100)
    elevation_change_m: float = Field(0, ge=-1000, le=1000)


class NetworkLossRequest(AnalysisContext):
    scenario: NetworkLossScenario = Field(default_factory=NetworkLossScenario)
    intervention: Literal["reduce_head", "clean_pipes", "reduce_local_resistance"] | None = None
