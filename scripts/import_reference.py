"""Справочные материалы заказчика → data/reference/reference.json.

Запуск: uv run python scripts/import_reference.py <каталог с xlsx> [выходной json]

Читает без изменений:
- «Бенчмаркинпо насосам.xlsx» — средневзвешенный УРЭ и КПД по классам подачи;
- «бенчмаркет электродвигателей.xlsx» — применяемые ЭД, аналоги и НДТ;
- «Алгоритм_определения_критичных_параметров_НА_с_прил_по_НРХ.xlsx» —
  критические отклонения, причины, меры и рабочие характеристики ЦНСн.

«Таблицы по КНС.xlsx» (критерии отклонений) перенесены вручную в
config/diagnostics.yaml и services/diagnostics.py (адресная диагностика).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl


PUMPS = "Бенчмаркинпо насосам.xlsx"
MOTORS = "бенчмаркет электродвигателей.xlsx"
ALGORITHM = "Алгоритм_определения_критичных_параметров_НА_с_прил_по_НРХ.xlsx"
BRANDS = ("current", "alternative_1", "alternative_2", "best")


def _text(value: object) -> str:
    # \x88 — испорченный в исходном файле дефис в марках («1ВАО\x88450S\x884»).
    return " ".join(str(value or "").replace("\x88", "-").split())


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(_text(value).replace(",", "."))
    except ValueError:
        return None


def _efficiency(value: object) -> dict:
    """КПД, % — число или диапазон «93,5-94,3»."""
    text = _text(value)
    if isinstance(value, float):
        text = f"{value:g}".replace(".", ",")
    if not text:
        return {"text": "", "min": None, "max": None}
    numbers = [float(item.replace(",", ".")) for item in re.findall(r"\d+(?:[.,]\d+)?", text)]
    return (
        {"text": text, "min": min(numbers), "max": max(numbers)}
        if numbers
        else {
            "text": text,
            "min": None,
            "max": None,
        }
    )


def pump_benchmark(path: Path) -> list[dict]:
    sheet = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    blocks: list[dict] = []
    block: dict | None = None
    for row in sheet.iter_rows(values_only=True):
        first = _text(row[0])
        if first and not first[0].isdigit() and first not in ("№№",):
            block = {
                "system": first,
                "objects": _text(row[1]),
                "flow_unit": "",
                "sec_unit": "",
                "rows": [],
            }
            blocks.append(block)
            continue
        if block is None:
            continue
        if first == "№№":
            block["flow_unit"] = "м³/сут" if "сут" in _text(row[1]) else "м³/ч"
            continue
        if not first and _text(row[3]).startswith("Средневзвеш"):
            block["sec_unit"] = "кВт·ч/м³" if "м3" in _text(row[3]) else "кВт·ч/т жидкости"
            continue
        if isinstance(row[0], (int, float)):
            block["rows"].append({
                "class": _text(row[1]),
                "current_pumps": _text(row[2]),
                "current_sec": _number(row[3]),
                "current_efficiency": _efficiency(row[4]),
                "efficient_pumps": _text(row[5]),
                "efficient_sec": _number(row[6]),
                "efficient_efficiency": _efficiency(row[7]),
                "note": _text(row[8]),
            })
    return blocks


def motor_benchmark(path: Path) -> list[dict]:
    sheet = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    groups: list[dict] = []
    group: dict | None = None
    item: dict | None = None
    for row in sheet.iter_rows(values_only=True):
        number, field = _text(row[1]), _text(row[2])
        values = [_text(value) for value in row[3:7]]
        raw = row[3:7]
        if re.fullmatch(r"\d+\.", number):
            group = {"id": number.rstrip("."), "type": values[0], "items": []}
            groups.append(group)
            continue
        if group is None:
            continue
        if re.fullmatch(r"\d+\.\d+\.", number) and field.startswith("Марка"):
            item = {
                "id": number.rstrip("."),
                "brands": dict(zip(BRANDS, values, strict=True)),
            }
            group["items"].append(item)
            continue
        if item is None:
            continue
        if field.startswith("Область"):
            item["application"] = values[0]
        elif field.startswith("Объекты"):
            item["objects"] = values[0]
        elif field.startswith("Мощность"):
            item["power_kw"] = _number(raw[0])
        elif field.startswith("Частота"):
            item["speed_rpm"] = [_number(value) for value in raw]
        elif field.startswith("КПД"):
            item["efficiency"] = dict(zip(BRANDS, map(_efficiency, raw), strict=True))
    return groups


def algorithm(path: Path) -> dict:
    book = openpyxl.load_workbook(path, data_only=True)
    sheet = book["алгор"]
    rows: list[dict] = []
    deviation = ""
    for row in sheet.iter_rows(min_row=12, values_only=True):
        if not isinstance(row[1], (int, float)):
            continue
        deviation = _text(row[2]) or deviation  # объединённые ячейки
        rows.append({
            "id": int(row[1]),
            "deviation": deviation,
            "cause": _text(row[3]),
            "action": _text(row[4]),
            "responsible": _text(row[5]),
            "note": _text(row[6]),
        })
    head = [_text(sheet.cell(row, 6).value) for row in range(1, 8)]
    appendix = book["прил"]
    ranges: list[dict] = []
    notes: list[str] = []
    for row in appendix.iter_rows(min_row=8, values_only=True):
        size = _text(row[0])
        if size.startswith("ЦНС") and isinstance(row[1], (int, float)):
            outlet_max = _text(row[7])
            match = re.match(r"([\d,.]+)\s*\(([\d,.]+)\)", outlet_max)
            ranges.append({
                "size": size,
                "head_m": float(row[1]),
                "q_min_m3h": _number(row[2]),
                "q_max_m3h": _number(row[3]),
                "p_in_min_atm": _number(row[4]),
                "p_in_max_atm": _number(row[5]),
                "p_out_min_atm": _number(row[6]),
                "p_out_max_atm": _number(match.group(1)) if match else _number(row[7]),
                "p_out_max_at_p_in_6_atm": _number(match.group(2)) if match else None,
            })
        elif size and not size.isdigit() and not size.startswith("Типоразмер") and len(size) > 20:
            notes.append(size)
    return {
        "title": _text(sheet["B10"].value),
        "approved_by": " ".join(item for item in head if item and "УТВЕРЖДАЮ" not in item),
        "rows": rows,
        "pump_ranges": ranges,
        "pump_range_notes": notes,
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    source = Path(argv[0])
    out = Path(argv[1]) if len(argv) > 1 else Path("data/reference/reference.json")
    payload = {
        "schema": "reference.v1",
        "sources": [PUMPS, MOTORS, ALGORITHM],
        "pump_benchmark": pump_benchmark(source / PUMPS),
        "motor_benchmark": motor_benchmark(source / MOTORS),
        "critical_parameters": algorithm(source / ALGORITHM),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(
        f"{out}: насосы {sum(len(b['rows']) for b in payload['pump_benchmark'])}, "
        f"ЭД {sum(len(g['items']) for g in payload['motor_benchmark'])}, "
        f"алгоритм {len(payload['critical_parameters']['rows'])}, "
        f"НРХ {len(payload['critical_parameters']['pump_ranges'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
