"""Геометрия водоводов из выгрузки реестра трубопроводов.

Источник — выгрузка реестра трубопроводов НГДУ: одна строка на участок
трубопровода. У участка есть наименование трубопровода, начало и конец,
назначение (подводящий, разводящий, внутриплощадочный), состояние, тип
трубы, наружный диаметр, толщина стенки, материал и внутреннее покрытие.

В расчёт берутся только участки в состоянии «В работе»: заменённые, разбитые,
ликвидированные и законсервированные участки остаются в реестре как история,
но вода по ним не идёт.

Связность сети записана в названиях. Трубопровод «A - Скв N - 1» идёт от узла
A к скважине N. Отвод от трубопровода P к скважине M называется
«(P) - Скв M - 1» и в графе «Начало участка» несёт имя P. Поэтому начало
трубопровода — либо узел (КНС, БГ, ВРП), либо конец другого трубопровода,
либо имя трубопровода, от которого сделан отвод.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path


ACTIVE_STATE = "В работе"

# Номер колонки в выгрузке реестра (строка заголовка начинается с «№»).
_COL = {
    "pipeline": 4,
    "start": 5,
    "end": 6,
    "control_point": 7,
    "line": 8,
    "pipeline_length": 9,
    "purpose": 11,
    "medium": 13,
    "temperature": 19,
    "p_work": 20,
    "section_start": 24,
    "section_end": 25,
    "section_length": 26,
    "section_commissioned": 27,
    "state": 28,
    "pipe_type": 29,
    "outer_diameter": 30,
    "wall": 31,
    "inner_coating": 32,
    "material": 34,
}

_WELL = re.compile(r"Скв\.?\s*([0-9]+[A-Za-zА-Яа-я]?)")
_LATIN_TO_CYRILLIC = str.maketrans("ABCDEGHKMOPTXabcdeghkmoptx", "АВСДЕГНКМОРТХавсдегнкмортх")


def normalize_well(text: object) -> str | None:
    """Номер скважины без префикса и с кириллическим суффиксом: «Скв 8323A» → «8323А»."""
    match = _WELL.search(str(text or ""))
    if not match:
        return None
    return match.group(1).upper().translate(_LATIN_TO_CYRILLIC)


def well_from_file_code(code: str) -> str:
    """Номер скважины из кода файла: «15150d» → «15150Д», «7583a» → «7583А»."""
    return code.strip().upper().translate(_LATIN_TO_CYRILLIC)


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except ValueError:
        return None


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


@dataclass(frozen=True)
class PipeSection:
    """Участок трубопровода с постоянной геометрией."""

    start_m: float
    end_m: float
    length_m: float
    outer_mm: float
    wall_mm: float
    pipe_type: str
    material: str
    inner_coating: str
    commissioned: date | None = None

    @property
    def inner_mm(self) -> float:
        return self.outer_mm - 2.0 * self.wall_mm

    @property
    def inner_m(self) -> float:
        return self.inner_mm / 1000.0


@dataclass
class Pipeline:
    """Трубопровод: цепочка действующих участков от начала к концу."""

    name: str
    start: str
    end: str
    purpose: str
    medium: str
    length_m: float
    temperature_c: float | None
    work_pressure_atm: float | None
    sections: list[PipeSection] = field(default_factory=list)

    @property
    def well(self) -> str | None:
        """Скважина в конце трубопровода, если трубопровод к скважине."""
        return normalize_well(self.end)

    @property
    def active_length_m(self) -> float:
        return sum(section.length_m for section in self.sections)


def _header_row(rows: list[tuple]) -> int:
    for index, row in enumerate(rows):
        if row and _text(row[0]) == "№":
            return index
    raise ValueError("в выгрузке реестра трубопроводов нет строки заголовка «№»")


def parse_pipelines(rows: list[tuple]) -> list[Pipeline]:
    """Трубопроводы с действующими участками из строк выгрузки реестра."""
    pipelines: dict[str, Pipeline] = {}
    for row in rows[_header_row(rows) + 1 :]:
        if not row or _text(row[0]) == "":
            continue
        if _text(row[_COL["state"]]) != ACTIVE_STATE:
            continue
        outer = _number(row[_COL["outer_diameter"]]) or 0.0
        wall = _number(row[_COL["wall"]]) or 0.0
        length = _number(row[_COL["section_length"]]) or 0.0
        if outer <= 0 or length <= 0 or outer - 2 * wall <= 0:
            continue
        name = _text(row[_COL["pipeline"]])
        pipeline = pipelines.get(name)
        if pipeline is None:
            pipeline = Pipeline(
                name=name,
                start=_text(row[_COL["start"]]),
                end=_text(row[_COL["end"]]),
                purpose=_text(row[_COL["purpose"]]),
                medium=_text(row[_COL["medium"]]),
                length_m=_number(row[_COL["pipeline_length"]]) or 0.0,
                temperature_c=_number(row[_COL["temperature"]]) or None,
                work_pressure_atm=_number(row[_COL["p_work"]]) or None,
            )
            pipelines[name] = pipeline
        pipeline.sections.append(
            PipeSection(
                start_m=_number(row[_COL["section_start"]]) or 0.0,
                end_m=_number(row[_COL["section_end"]]) or 0.0,
                length_m=length,
                outer_mm=outer,
                wall_mm=wall,
                pipe_type=_text(row[_COL["pipe_type"]]),
                material=_text(row[_COL["material"]]),
                inner_coating=_text(row[_COL["inner_coating"]]),
                commissioned=_date(row[_COL["section_commissioned"]]),
            )
        )
    for pipeline in pipelines.values():
        pipeline.sections.sort(key=lambda section: section.start_m)
    return list(pipelines.values())


def read_pipelines(path: Path, sheet: str) -> list[Pipeline]:
    """Прочитать лист выгрузки реестра трубопроводов."""
    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        rows = list(workbook[sheet].iter_rows(values_only=True))
    finally:
        workbook.close()
    return parse_pipelines(rows)
