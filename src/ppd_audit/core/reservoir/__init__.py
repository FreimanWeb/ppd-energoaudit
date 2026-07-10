"""Подключаемый модуль отклика пласта (интерфейс + реализации)."""

from .base import ReservoirInput, ReservoirModel, ReservoirResult
from .crm import CRMLite
from .demo import DemoReservoir

__all__ = ["ReservoirInput", "ReservoirResult", "ReservoirModel",
           "DemoReservoir", "CRMLite", "get_model"]


def get_model(name: str = "demo") -> ReservoirModel:
    """Фабрика модели по имени: 'demo' | 'crm-lite'."""
    models = {"demo": DemoReservoir, "crm-lite": CRMLite}
    if name not in models:
        raise ValueError(f"неизвестная модель пласта: {name}; доступно: {list(models)}")
    return models[name]()
