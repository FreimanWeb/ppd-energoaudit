"""Цифровой реестр организационно-технических мероприятий + авто-ТЭО.

ТЗ (треб. 5): расчёт технического, энергетического и экономического эффекта;
классификация «быстрые победы / условно-окупаемые». Энергоэффект — из годовых
потерь ядра (44)-(47); экономический = ×тариф; окупаемость = CAPEX/эффект.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from ..core.audit import AuditResult


class MeasureClass(str, Enum):
    quick_win = "быстрая победа"          # режимные/организационные, без CAPEX
    conditional = "условно-окупаемое"     # требует CAPEX


@dataclass
class Measure:
    id: str
    name: str
    cls: MeasureClass
    addresses: str                        # какие потери закрывает
    capex_krub: float = 0.0               # тыс. руб
    # сколько кВт·ч/год экономит — функция от результата аудита
    saving_fn: Optional[Callable[[AuditResult], float]] = None
    applicable_fn: Optional[Callable[[AuditResult], bool]] = None


@dataclass
class MeasureEvaluation:
    measure_id: str
    name: str
    cls: str
    energy_saving_kwh: float
    money_saving_krub: float              # тыс. руб/год
    capex_krub: float
    payback_years: Optional[float]        # None если без CAPEX/нет эффекта
    note: str = ""


def _throttle_saving(a: AuditResult) -> float:
    return a.dw_throttle or 0.0


def _cyclic_saving(a: AuditResult) -> float:
    # экономия перехода на непрерывный режим ≈ потери на дросселирование/циклику
    return (a.dw_throttle or 0.0) * 0.5


def _efficiency_saving(a: AuditResult) -> float:
    return a.dw_efficiency or 0.0


# Библиотека типовых мероприятий (растёт по ходу).
CATALOG: list[Measure] = [
    Measure("throttle_down", "Снижение дросселирования (открытие задвижки/штуцера)",
            MeasureClass.quick_win, "ΔW_дрос (45)", 0.0,
            saving_fn=_throttle_saving,
            applicable_fn=lambda a: (a.dw_throttle or 0) > 0),
    Measure("continuous_mode", "Непрерывный равномерный режим вместо циклического",
            MeasureClass.quick_win, "ΔW_ц (46)", 0.0,
            saving_fn=_cyclic_saving,
            applicable_fn=lambda a: (a.dw_throttle or 0) > 0),
    Measure("vfd", "Внедрение ПЧ (частотное регулирование)",
            MeasureClass.conditional, "дросселирование/циклика", 7000.0,
            saving_fn=lambda a: (a.dw_throttle or 0) + _cyclic_saving(a),
            applicable_fn=lambda a: not a.spec.vfd and (a.dw_throttle or 0) > 0),
    Measure("motor_resize", "Замена ЭД на адекватную мощность",
            MeasureClass.conditional, "ΔP_ЭД (41), низкий K_з", 2500.0,
            saving_fn=lambda a: max(a.dw_efficiency * 0.15, 0.0),
            applicable_fn=lambda a: a.load_factor < 0.7),
    Measure("pump_overhaul", "Капремонт/замена насосного агрегата",
            MeasureClass.conditional, "ΔP_изн (42), снижение КПД", 5000.0,
            saving_fn=lambda a: a.dw_efficiency * 0.5,
            applicable_fn=lambda a: a.regime.eta_unit < 0.9 * a.regime.eta_nom),
]


def evaluate(measure: Measure, audit: AuditResult, tariff: float = 4.68) -> MeasureEvaluation:
    """ТЭО мероприятия для агрегата: энергия, деньги, окупаемость."""
    energy = measure.saving_fn(audit) if measure.saving_fn else 0.0
    money_krub = energy * tariff / 1000.0
    payback = (measure.capex_krub / money_krub) if money_krub > 0 and measure.capex_krub > 0 else None
    return MeasureEvaluation(
        measure_id=measure.id, name=measure.name, cls=measure.cls.value,
        energy_saving_kwh=round(energy, 1), money_saving_krub=round(money_krub, 1),
        capex_krub=measure.capex_krub,
        payback_years=round(payback, 2) if payback else None)


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
