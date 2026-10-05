"""Входы расчётных представлений: единый выбор источника режима."""

from typing import Literal

from pydantic import BaseModel, Field


class AnalysisContext(BaseModel):
    source: Literal["telemetry", "field_trip"] = "telemetry"
    day: str | None = None
    timestamp: str | None = None


class MeasuresRequest(AnalysisContext):
    horizon_years: int = Field(3, ge=1, le=10)
    discount_rate: float = Field(0.15, ge=0, le=0.6)
    period_days: int = Field(30, ge=1, le=365)
    basis: Literal["annual", "forecast"] = "annual"
