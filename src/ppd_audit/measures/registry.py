"""Цифровой реестр организационно-технических мероприятий + авто-ТЭО.

ТЗ (треб. 5): расчёт технического, энергетического и экономического эффекта;
классификация «быстрые победы / условно-окупаемые». Энергоэффект — из годовых
потерь ядра (44)-(47); экономический = ×тариф; окупаемость = CAPEX/эффект.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

from ..core.audit import AuditResult
from ..core.pump import PumpingDecomposition


class MeasureClass(StrEnum):
    quick_win = "быстрая победа"  # режимные/организационные, без CAPEX
    conditional = "условно-окупаемое"  # требует CAPEX


@dataclass
class Measure:
    id: str
    name: str
    cls: MeasureClass
    addresses: str  # какие потери закрывает
    capex_krub: float = 0.0  # тыс. руб
    # сколько кВт·ч/год экономит — функция от результата аудита
    saving_fn: Callable[[AuditResult], float] | None = None
    applicable_fn: Callable[[AuditResult], bool] | None = None


@dataclass
class MeasureEvaluation:
    measure_id: str
    name: str
    cls: str
    energy_saving_kwh: float
    money_saving_krub: float  # тыс. руб/год
    capex_krub: float
    payback_years: float | None  # None если без CAPEX/нет эффекта
    note: str = ""


def _throttle_saving(a: AuditResult) -> float:
    return a.dw_throttle or 0.0


def _pumping_component_saving(
    audit: AuditResult, component: Callable[[PumpingDecomposition], float]
) -> float:
    if not isinstance(audit.decomposition, PumpingDecomposition):
        return 0.0
    if audit.spec is None or audit.spec.regime is None or audit.spec.regime.t_year is None:
        return 0.0
    return max(component(audit.decomposition), 0.0) * audit.spec.regime.t_year


def _suboptimal_saving(audit: AuditResult) -> float:
    return _pumping_component_saving(audit, lambda decomposition: decomposition.dp_suboptimal)


def _motor_saving(audit: AuditResult) -> float:
    return _pumping_component_saving(audit, lambda decomposition: decomposition.dp_motor)


def _wear_saving(audit: AuditResult) -> float:
    return _pumping_component_saving(audit, lambda decomposition: decomposition.dp_wear)


# Библиотека типовых мероприятий (растёт по ходу).
CATALOG: list[Measure] = [
    Measure(
        "throttle_down",
        "Снижение дросселирования (открытие задвижки/штуцера)",
        MeasureClass.quick_win,
        "ΔW_дрос (45)",
        0.0,
        saving_fn=_throttle_saving,
        applicable_fn=lambda a: (a.dw_throttle or 0) > 0,
    ),
    Measure(
        "pump_working_point",
        "Оптимизация рабочей точки насоса",
        MeasureClass.quick_win,
        "ΔP_неопт (39)",
        0.0,
        saving_fn=_suboptimal_saving,
        applicable_fn=lambda a: _suboptimal_saving(a) > 0,
    ),
    Measure(
        "vfd",
        "Внедрение ПЧ (частотное регулирование)",
        MeasureClass.conditional,
        "ΔW_дрос (45)",
        7000.0,
        saving_fn=_throttle_saving,
        applicable_fn=lambda a: a.spec is not None and not a.spec.vfd and (a.dw_throttle or 0) > 0,
    ),
    Measure(
        "motor_resize",
        "Замена ЭД на адекватную мощность",
        MeasureClass.conditional,
        "ΔP_ЭД (41)",
        2500.0,
        saving_fn=_motor_saving,
        applicable_fn=lambda a: _motor_saving(a) > 0,
    ),
    Measure(
        "pump_overhaul",
        "Капремонт/замена насосного агрегата",
        MeasureClass.conditional,
        "ΔP_изн (42)",
        5000.0,
        saving_fn=_wear_saving,
        applicable_fn=lambda a: _wear_saving(a) > 0,
    ),
]


def evaluate(measure: Measure, audit: AuditResult, tariff: float = 4.68) -> MeasureEvaluation:
    """ТЭО мероприятия для агрегата: энергия, деньги, окупаемость."""
    energy = measure.saving_fn(audit) if measure.saving_fn else 0.0
    money_krub = energy * tariff / 1000.0
    payback = (
        (measure.capex_krub / money_krub) if money_krub > 0 and measure.capex_krub > 0 else None
    )
    return MeasureEvaluation(
        measure_id=measure.id,
        name=measure.name,
        cls=measure.cls.value,
        energy_saving_kwh=round(energy, 1),
        money_saving_krub=round(money_krub, 1),
        capex_krub=measure.capex_krub,
        payback_years=round(payback, 2) if payback else None,
    )


def suggest_measures(audit: AuditResult, tariff: float = 4.68) -> list[MeasureEvaluation]:
    """Авто-подбор применимых мероприятий с ТЭО, отсортированных по эффекту."""
    out = []
    for m in CATALOG:
        if m.applicable_fn and not m.applicable_fn(audit):
            continue
        ev = evaluate(m, audit, tariff)
        if ev.energy_saving_kwh > 0:
            out.append(ev)
    return sorted(out, key=lambda e: e.energy_saving_kwh, reverse=True)
