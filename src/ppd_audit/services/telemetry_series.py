"""Подготовка рядов телеметрии к отображению."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

import pandas as pd


_METRIC_LABELS = {
    "density": "Плотность",
    "energy": "Энергия за сутки",
    "flow_rate": "Q",
    "p_bg": "p_БГ",
    "p_in": "p_вх",
    "p_out": "p_вых",
    "power": "P_эл",
    "q_day": "Q_сут",
    "runtime": "Моточасы за сутки",
    "viscosity": "Вязкость",
}
_DAILY_TOTALS = {"energy", "q_day", "runtime"}


def telemetry_series(rows: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    """Сгруппировать сырые точки по единицам измерения для независимых графиков."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["metric"] in _DAILY_TOTALS:
            continue
        label = _METRIC_LABELS.get(row["metric"], row["metric"])
        if row["is_station"]:
            label += " (станция)"
        grouped[row["unit"]].append({
            "Время": datetime.fromisoformat(row["timestamp"]),
            "Показатель": label,
            "Значение": row["value"],
        })
    return {
        unit: pd
        .DataFrame(points)
        .pivot_table(index="Время", columns="Показатель", values="Значение", aggfunc="last")
        .reset_index()
        for unit, points in grouped.items()
    }
