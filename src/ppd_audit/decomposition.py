"""Сводная декомпозиция УРЭ и цифровая карта потерь.

Собирает потери мощности агрегата (из core.audit) в единую структуру: полезная
мощность + статьи потерь с долями, годовой энергией и стоимостью. Используется
дашбордом (карта потерь) и отчётами.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .core.audit import AuditResult


@dataclass
class LossItem:
    name: str
    power_kw: float
    share: float            # доля от P_эл
    annual_kwh: float
    annual_rub: float
    category: str           # "полезная" | "потеря"


@dataclass
class LossMap:
    aggregate_id: str
    p_electric: float
    useful_kw: float
    items: list[LossItem] = field(default_factory=list)

    @property
    def total_loss_kw(self) -> float:
        return sum(i.power_kw for i in self.items if i.category == "потеря")


def _components(audit: AuditResult) -> tuple[float, list[tuple[str, float]]]:
    """(полезная мощность, [(статья, кВт)]) из декомпозиции (КНС/перекачка)."""
    d = audit.decomposition
    if d is None:
        return audit.regime.p_hydraulic, []
    if hasattr(d, "p_bg_useful"):       # КНС (31-36)
        return d.p_bg_useful, [
            ("Потери КПД", d.dp_efficiency), ("Номинальные", d.dp_nominal),
            ("Дросселирование", d.dp_na_throttle), ("Гидравл. насос→БГ", d.dp_hydraulic)]
    return audit.regime.p_hydraulic, [     # перекачка (37-42)
        ("Износ", d.dp_wear), ("Неоптимальная подача", d.dp_suboptimal),
        ("Завышенная мощность ЭД", d.dp_motor), ("Вязкость", d.dp_viscosity),
        ("Номинальные", d.dp_nominal)]


def build_loss_map(audit: AuditResult, tariff: float = 4.68,
                   t_year: float = 8760.0) -> LossMap:
    """Цифровая карта потерь агрегата с годовой энергией и стоимостью."""
    p_el = audit.regime.p_electric
    t_year = (audit.spec and audit.spec.regime and audit.spec.regime.t_year) or t_year
    useful, comps = _components(audit)
    comps = [(n, v) for n, v in comps if abs(v) > 1e-9]

    items = [LossItem("Полезная мощность", useful, useful / p_el,
                      useful * t_year, useful * t_year * tariff, "полезная")]
    for name, kw in comps:
        items.append(LossItem(name, kw, kw / p_el, kw * t_year,
                              kw * t_year * tariff, "потеря"))
    return LossMap(aggregate_id=audit.aggregate_id, p_electric=p_el,
                   useful_kw=useful, items=items)
