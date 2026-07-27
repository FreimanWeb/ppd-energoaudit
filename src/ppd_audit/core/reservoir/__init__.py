"""Подключаемый модуль отклика пласта (интерфейс + реализации) + прогноз закачки."""

from .base import ReservoirInput, ReservoirModel, ReservoirResult
from .crm import CRMLite
from .demo import DemoReservoir
from .forecast import (ForecastPoint, ForecastResult, aggregate_daily_to_periods,
                       forecast_injection)


__all__ = [
    "ReservoirInput",
    "ReservoirResult",
    "ReservoirModel",
    "DemoReservoir",
    "CRMLite",
    "get_model",
    "ForecastPoint",
    "ForecastResult",
    "forecast_injection",
    "aggregate_daily_to_periods",
]


def get_model(name: str = "demo") -> ReservoirModel:
    """Фабрика модели по имени: 'demo' | 'crm-lite'."""
    if name == "demo":
        return DemoReservoir()
    if name == "crm-lite":
        return CRMLite()
    raise ValueError(f"неизвестная модель пласта: {name}; доступно: ['demo', 'crm-lite']")
