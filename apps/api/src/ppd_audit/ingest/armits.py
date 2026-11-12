"""Read-only import of the KNS-54 ARMITС registry; Q/P remain unconverted source values."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

import openpyxl


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _number(value: Any, location: str, *, optional: bool = False) -> float | None:
    if value is None or _text(value) == "":
        if optional:
            return None
        raise ValueError(f"{location}: отсутствует обязательное число")
    try:
        number = float(_text(value).replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{location}: не число: {value!r}") from exc
    if isinstance(value, bool) or not math.isfinite(number):
        raise ValueError(f"{location}: требуется конечное число: {value!r}")
    return number


def _headers(sheet: Any, row: int, expected: dict[int, str]) -> None:
    values = next(sheet.iter_rows(min_row=row, max_row=row, values_only=True))
    for column, name in expected.items():
        if column >= len(values) or _text(values[column]) != name:
            raise ValueError(
                f"{sheet.title}, строка {row}, столбец {column + 1}: ожидался «{name}»"
            )


def read_armits(path: Path) -> dict[str, Any]:
    """Import active sections and all well/formation rows without changing the workbook."""
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for name in ("54 труб", "54 скв"):
            if name not in workbook.sheetnames:
                raise ValueError(f"{path.name}: отсутствует лист «{name}»")
        pipes, well_sheet = workbook["54 труб"], workbook["54 скв"]
        _headers(
            pipes,
            5,
            {
                2: "Новый идентификатор",
                4: "Наименование трубопровода",
                5: "Начало участка",
                6: "Конец участка",
                11: "Назначение",
                13: "Транспортируемая среда",
                16: "Дебит жидкости",
                20: "Давление рабочее",
                24: "Начало участка",
                25: "Конец участка",
                26: "Длина участка",
                28: "Состояние",
                29: "Тип трубы",
                30: "Диаметр",
                31: "Толщина стенки",
                32: "Внутр. покрытие",
                34: "Материал",
            },
        )
        _headers(
            well_sheet,
            2,
            {
                2: "Скваж",
                6: "Q_ф",
                11: "Ру_до_шт",
                12: "Ру_после_шт",
                17: "Пласт",
            },
        )
        exported = pipes["D2"].value
        if isinstance(exported, (date, datetime)):
            exported_at = exported.strftime("%Y-%m-%d")
        else:
            try:
                exported_at = datetime.strptime(_text(exported), "%d.%m.%Y").date().isoformat()
            except ValueError as exc:
                raise ValueError(f"54 труб!D2: неизвестная дата выгрузки {exported!r}") from exc

        segments = []
        statuses: Counter[str] = Counter()
        for row_number, row in enumerate(pipes.iter_rows(min_row=6, values_only=True), 6):
            if not any(value is not None for value in row):
                continue
            status = _text(row[28])
            statuses[status] += 1
            if status != "В работе":
                continue
            location = f"54 труб, строка {row_number}"
            pipeline_id, from_node, to_node = (_text(row[i]) for i in (2, 5, 6))
            if not all((pipeline_id, from_node, to_node)):
                raise ValueError(f"{location}: отсутствует ID или именованный конец участка")
            numbers = {
                name: _number(row[index], f"{location}, {name}")
                for name, index in (
                    ("start_m", 24),
                    ("end_m", 25),
                    ("length_m", 26),
                    ("outer_diameter_mm", 30),
                    ("wall_thickness_mm", 31),
                )
            }
            start, end, length, diameter, wall = numbers.values()
            if start < 0 or end <= start or length <= 0:
                raise ValueError(f"{location}: неверные координаты/длина участка")
            if not math.isclose(end - start, length, rel_tol=1e-6, abs_tol=0.01):
                raise ValueError(f"{location}: длина AA не соответствует Z − Y")
            if wall <= 0 or diameter <= 2 * wall:
                raise ValueError(f"{location}: неположительный внутренний диаметр или стенка")
            segments.append({
                "id": f"{pipeline_id}:{row_number}",
                "pipeline_id": pipeline_id,
                "pipeline_name": _text(row[4]),
                "from_node": from_node,
                "to_node": to_node,
                **numbers,
                "material": _text(row[34]),
                "pipe_type": _text(row[29]),
                "inner_coating": _text(row[32]),
                "medium": _text(row[13]),
                "purpose": _text(row[11]),
                "source_row": row_number,
                "source_sheet": pipes.title,
                "registry_flow": _number(row[16], f"{location}, Q", optional=True),
                "registry_pressure": _number(row[20], f"{location}, P", optional=True),
            })

        wells = []
        well_id = ""
        for row_number, row in enumerate(well_sheet.iter_rows(min_row=3, values_only=True), 3):
            if not any(value is not None and _text(value) for value in row):
                continue
            explicit_id, formation = _text(row[2]), _text(row[17])
            if explicit_id:
                well_id = explicit_id
            elif not formation:
                continue
            if not well_id:
                raise ValueError(f"54 скв, строка {row_number}: пласт без предшествующей скважины")
            location = f"54 скв, строка {row_number}"
            wells.append({
                "id": well_id,
                "formation": formation or None,
                "source_row": row_number,
                "source_sheet": well_sheet.title,
                "raw_flow": _number(row[6], f"{location}, Q_ф", optional=True),
                "raw_pressure_before": _number(row[11], f"{location}, Ру_до_шт", optional=True),
                "raw_pressure_after": _number(row[12], f"{location}, Ру_после_шт", optional=True),
            })
    finally:
        workbook.close()

    if not segments or not wells:
        raise ValueError(f"{path.name}: нет действующих участков или скважин КНС-54")
    return {
        "object_id": "kns54an",
        "source_file": path.name,
        "exported_at": exported_at,
        "segments": segments,
        "wells": wells,
        "summary": {
            "pipeline_rows": sum(statuses.values()),
            "statuses": dict(statuses),
            "active_sections": len(segments),
            "active_pipelines": len({item["pipeline_id"] for item in segments}),
            "unique_wells": len({item["id"] for item in wells}),
            "well_formation_rows": len(wells),
        },
        "warnings": [
            "Длины и координаты — в метрах, диаметр и стенка — в миллиметрах: сумма длин "
            "участков совпадает с длиной трубопровода, типоразмеры — с сортаментом.",
            "Диаметр принят наружным; толщина внутреннего покрытия не указана.",
            "Q/P сохранены без пересчёта: единицы, период и смысл нулей не подтверждены.",
            "Дата exported_at относится к листу трубопроводов, не к измерениям скважин.",
            "Несколько участков одного pipeline_id — интервалы одной трубы, не параллельные ветви.",
            "Именованные концы могут ссылаться на родительский трубопровод; "
            "точки врезки и связность требуют проверки.",
            "В строках-продолжениях сохранён номер предыдущей скважины; "
            "расход и давления не скопированы и не распределены по пластам.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.resolve() == args.workbook.resolve():
        parser.error("выходной JSON не может заменять исходный Excel")
    result = read_armits(args.workbook)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
