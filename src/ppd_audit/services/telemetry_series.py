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
_HELD_METRICS = {"p_in", "p_out", "p_bg", "power"}


def telemetry_series(
    rows: list[dict[str, Any]], *, start: datetime | None = None, end: datetime | None = None
) -> dict[str, pd.DataFrame]:
    """Сгруппировать события телеметрии; давления и P_эл действуют до изменения."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    previous_states: dict[tuple[str, bool], dict[str, Any]] = {}
    latest_states: dict[tuple[str, bool], dict[str, Any]] = {}
    state_at_start: set[tuple[str, bool]] = set()
    state_at_end: set[tuple[str, bool]] = set()
    for row in rows:
        if row["metric"] in _DAILY_TOTALS:
            continue
        timestamp = datetime.fromisoformat(row["timestamp"])
        pressure_key = (row["metric"], bool(row["is_station"]))
        if row["metric"] in _HELD_METRICS and start is not None and timestamp < start:
            previous_states[pressure_key] = row
            latest_states[pressure_key] = row
            continue
        if end is not None and (
            timestamp > end or (timestamp == end and row["metric"] not in _HELD_METRICS)
        ):
            continue
        if row["metric"] in _HELD_METRICS and start is not None and timestamp == start:
            state_at_start.add(pressure_key)
        if row["metric"] in _HELD_METRICS:
            latest_states[pressure_key] = row
            if end is not None and timestamp == end:
                state_at_end.add(pressure_key)
        label = _METRIC_LABELS.get(row["metric"], row["metric"])
        if row["is_station"]:
            label += " (станция)"
        grouped[row["unit"]].append({
            "Время": timestamp,
            "Показатель": label,
            "Значение": row["value"],
        })
    if start is not None:
        for pressure_key, row in previous_states.items():
            if pressure_key in state_at_start:
                continue
            label = _METRIC_LABELS[row["metric"]]
            if row["is_station"]:
                label += " (станция)"
            grouped[row["unit"]].append({
                "Время": start,
                "Показатель": label,
                "Значение": row["value"],
            })
    if end is not None:
        for pressure_key, row in latest_states.items():
            if pressure_key in state_at_end:
                continue
            label = _METRIC_LABELS[row["metric"]]
            if row["is_station"]:
                label += " (станция)"
            grouped[row["unit"]].append({
                "Время": end,
                "Показатель": label,
                "Значение": row["value"],
            })
    return {
        unit: pd.DataFrame(points).sort_values(["Показатель", "Время"]).reset_index(drop=True)
        for unit, points in grouped.items()
    }
