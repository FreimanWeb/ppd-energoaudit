"""Интерфейс подключаемого модуля отклика пласта.

ТЗ (ред. 18.06): конкретная модель не предписана — интерфейс заменяем. Вход: ряды
закачки/добычи по скважинам. Выход: матрица связностей и эффективная закачка.
Реализации: DemoReservoir (заглушка), CRMLite (CRM-регрессия). Возможны внешние
(модуль/HTTP) через тот же протокол.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ReservoirInput:
    """Ряды по скважинам (одинаковой длины по времени)."""
    injectors: list[str]
    producers: list[str]
    injection: dict[str, list[float]]    # inj_id → ряд закачки, м³/сут
    production: dict[str, list[float]] = field(default_factory=dict)  # prod_id → ряд добычи


@dataclass
class ReservoirResult:
    connectivity: dict[str, dict[str, float]]   # prod → {inj → λ (доля)}
    effective_injection: dict[str, float]       # inj → эффективная закачка, м³/сут
    model: str
    estimate: bool = True
    note: str = ""


@runtime_checkable
class ReservoirModel(Protocol):
    """Контракт модели отклика пласта."""
    name: str

    def fit(self, data: ReservoirInput) -> ReservoirResult: ...
