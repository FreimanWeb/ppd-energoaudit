"""Пригодность измерения не определяется величиной или числовой меткой качества."""

from math import isfinite
from typing import Any, Mapping


def confirmed_quality(quality: str | None) -> bool:
    return quality in (None, "", "good", "ready")


def usable_measurement(row: Mapping[str, Any]) -> bool:
    if not confirmed_quality(row["quality"]):
        return False
    value = float(row["value"])
    if not isfinite(value) or value < 0:
        return False
    if row["metric"] == "density" and value == 0:
        return False
    if row["metric"] == "runtime" and value > 24:
        return False
    return row["unit"] != "не подтверждена"
