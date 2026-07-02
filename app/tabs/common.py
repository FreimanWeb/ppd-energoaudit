"""Общее для вкладок: контекст выбранного агрегата, форматирование, палитра статусов."""

from __future__ import annotations

import re
from dataclasses import dataclass

WATER_EMOJI = {"пресная": "💧", "агрессивная": "🧪", "пластовая": "🛢️"}
STATUS_BG = {"✓": "#d7f5dd", "⚠": "#fff3cd", "✗": "#f8d7da", "—": "#eeeeee"}


@dataclass
class Ctx:
    """Всё, что нужно вкладке: выбранный объект/агрегат и результат аудита."""
    object_id: str
    agg_id: str
    obj: object          # ObjectSpec
    agg: object          # AggregateSpec
    audit: object        # AuditResult
    tariff: float


def fmt(x, nd: int = 2) -> str:
    """Формат числа ru-RU: 53 242,90; None → «—»."""
    if x is None or isinstance(x, str):
        return x if isinstance(x, str) else "—"
    s = f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")
    return s


def clean_nums(s: str) -> str:
    """Округлить длинные десятичные хвосты в строке (0.8335950000001 → 0.8336)."""
    return re.sub(r"-?\d+\.\d+", lambda m: f"{float(m.group()):.4g}", str(s))


def loss_components(audit) -> tuple[float, list[tuple[str, float]]]:
    """(полезная мощность, [(подпись потери, кВт)]). Сумма = P_эл."""
    d = audit.decomposition
    if d is None:
        return audit.regime.p_hydraulic, []
    if hasattr(d, "p_bg_useful"):       # КНС (31-36)
        return d.p_bg_useful, [
            ("Потери КПД", d.dp_efficiency), ("Номинальные", d.dp_nominal),
            ("Дросселирование", d.dp_na_throttle), ("Гидравл. насос→БГ", d.dp_hydraulic)]
    # перекачка (37-42)
    return audit.regime.p_hydraulic, [
        ("Износ", d.dp_wear), ("Неоптим. подача", d.dp_suboptimal),
        ("Завыш. мощность ЭД", d.dp_motor), ("Вязкость", d.dp_viscosity),
        ("Номинальные", d.dp_nominal)]
