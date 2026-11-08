"""Журналы выявленных дефектов 1С ТОИР по насосным агрегатам (xls).

Один файл — один агрегат, имя файла «<объект> <агрегат>.xls»
(«КНС-54 НА-1.xls»). Колонки: документ (номер и дата), отказавший элемент,
типовой дефект, вид дефекта, непосредственная причина, критичность, статус.
Сопоставление имени объекта с кодом в приложении — ``config/toir.yaml``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml


_DOCUMENT = re.compile(r"(\d{6,})\s+от\s+(\d{2}\.\d{2}\.\d{4}(?:\s+[\d:]+)?)")


@dataclass(frozen=True)
class Defect:
    number: str
    detected_at: datetime | None
    element: str
    defect: str
    kind: str
    cause: str
    criticality: str
    status: str


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _document(text: str) -> tuple[str, datetime | None]:
    match = _DOCUMENT.search(text)
    if not match:
        return text, None
    stamp = match.group(2)
    for pattern in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
        try:
            return match.group(1), datetime.strptime(stamp, pattern)
        except ValueError:
            continue
    return match.group(1), None


def read_defects(path: Path) -> list[Defect]:
    import xlrd

    sheet = xlrd.open_workbook(path).sheet_by_index(0)
    defects = []
    for row in range(1, sheet.nrows):
        values = [_text(value) for value in sheet.row_values(row)]
        if not values or not values[0].startswith("Выявленный дефект"):
            continue
        number, detected = _document(values[0])
        defects.append(Defect(number, detected, *(values[1:7] + [""] * (7 - len(values)))[:6]))
    return sorted(defects, key=lambda item: item.detected_at or datetime.min, reverse=True)


def toir_files(root: Path, config: Path) -> dict[tuple[str, str], Path]:
    """(код объекта, код агрегата) → файл журнала."""
    if not root.is_dir() or not config.is_file():
        return {}
    raw = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    plants = raw.get("plants") or {}
    found = {}
    for path in sorted(root.glob("*.xls")):
        for prefix, spec in plants.items():
            if not path.stem.startswith(prefix + " "):
                continue
            unit = path.stem[len(prefix) + 1 :].strip()
            aggregate = (spec.get("aggregates") or {}).get(unit, unit)
            found[(spec["plant"], aggregate)] = path
    return found
