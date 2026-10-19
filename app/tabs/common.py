"""Общее для вкладок: контекст выбранного агрегата и форматирование чисел."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from ppd_audit.services.analysis import loss_components  # noqa: F401


_LOSS_DICTIONARY = json.loads(
    (Path(__file__).resolve().parents[2] / "shared" / "loss-labels.json").read_text()
)
LOSS_LABELS = _LOSS_DICTIONARY["labels"]


def loss_label(name: str) -> str:
    return LOSS_LABELS.get(_LOSS_DICTIONARY["aliases"].get(name), name)


@dataclass
class Ctx:
    """Всё, что нужно вкладке: выбранный объект/агрегат и результат аудита."""

    object_id: str
    agg_id: str
    obj: object  # ObjectSpec
    agg: object  # AggregateSpec
    audit: object  # AuditResult
    tariff: float
    selected_date: date
    snapshot_timestamp: datetime
    scope: object  # ResultScope
    source: str = "telemetry"
    quality: object | None = None


def fmt(x, nd: int = 2) -> str:
    """Формат числа ru-RU: 53 242,90; None → «—»."""
    if x is None or isinstance(x, str):
        return x if isinstance(x, str) else "—"
    s = f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")
    return s


def clean_nums(s: str) -> str:
    """Округлить длинные десятичные хвосты в строке (0.8335950000001 → 0.8336)."""
    return re.sub(r"-?\d+\.\d+", lambda m: f"{float(m.group()):.4g}", str(s))
