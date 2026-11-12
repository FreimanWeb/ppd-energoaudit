"""Read well measurements from ARMIТС XLS exports without extracting the ZIP.

Pressures retain the source unit «атм»; monthly rows are not daily telemetry.
The current snapshot date is the export date, not a proven measurement date.
"""

from __future__ import annotations

import calendar
import math
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import xlrd

from .pipelines import well_from_file_code


_PLANTS = {
    "54 Азнакаевскнефть": "kns54an",
    "97-2 Елховнефть": "kns97pren",
    "ОПУ Джалильнефть": "knsopu",
}
_MONTHLY = {
    1: ("flow_m3_day", "м³/сут", "monthly_actual"),
    5: ("p_well", "атм", "monthly_actual"),
    6: ("p_bg", "атм", "monthly_actual"),
    7: ("p_reservoir", "атм", "monthly_actual"),
    8: ("p_bottomhole", "атм", "monthly_actual"),
    10: ("flow_m3_day", "м³/сут", "monthly_reported"),
    11: ("injection_volume_m3", "м³", "monthly_reported"),
    12: ("runtime_hours", "ч", "monthly_reported"),
    13: ("downtime_hours", "ч", "monthly_reported"),
    14: ("restricted_hours", "ч", "monthly_reported"),
    15: ("p_well", "атм", "monthly_reported"),
}


def _check_headers(sheet: Any, row: int, expected: dict[int, str]) -> None:
    for column, value in expected.items():
        if (
            sheet.nrows <= row
            or sheet.ncols <= column
            or str(sheet.cell_value(row, column)).strip() != value
        ):
            raise ValueError(f"{sheet.name}: неизвестный заголовок, строка {row + 1}")


def _measurement_number(value: Any, location: str) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(str(value).strip().replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{location}: не число {value!r}") from exc
    if isinstance(value, bool) or not math.isfinite(number) or number < 0:
        raise ValueError(f"{location}: требуется конечное неотрицательное число: {value!r}")
    return number


def _read_workbook(book: Any, source_file: str, plant: str) -> list[dict[str, Any]]:
    current = book.sheet_by_name("Режим")
    header = str(current.cell_value(0, 0))
    identity = re.search(r"СКВАЖИ[HН]Е\s+(\S+).*?на\s+(\d{2}/\d{2}/\d{4})", header)
    if not identity:
        raise ValueError(f"{source_file}: неизвестный номер скважины/дата выгрузки")
    well, exported = identity.groups()
    exported = datetime.strptime(exported, "%d/%m/%Y").date().isoformat()
    base = {
        "plant_code": plant,
        "well_code": well,
        "source_file": source_file,
        "exported_at": exported,
    }
    records = []

    def add(sheet, row, value, metric, unit, observed, grain, kind, study_type=""):
        location = f"{source_file}, {sheet.name}, строка {row + 1}"
        number = _measurement_number(value, location)
        if number is not None:
            if metric == "density_kgm3":
                number *= 1000
            records.append({
                **base,
                "observed_at": observed,
                "grain": grain,
                "record_kind": kind,
                "metric": metric,
                "value": number,
                "unit": unit,
                "study_type": study_type,
                "source_sheet": sheet.name,
                "source_row": row + 1,
            })

    _check_headers(current, 8, {0: "Qжид.факт", 2: "м3/сут", 3: "Ру до шт.", 5: "атм"})
    add(
        current,
        8,
        current.cell_value(8, 1),
        "flow_m3_day",
        "м³/сут",
        exported,
        "snapshot",
        "current",
    )
    add(
        current,
        8,
        current.cell_value(8, 4),
        "p_well_before_choke",
        "атм",
        exported,
        "snapshot",
        "current",
    )
    after = str(current.cell_value(8, 6)).strip()
    if after:
        match = re.fullmatch(r"после\s+(.+)", after)
        if not match:
            raise ValueError(f"{source_file}: неизвестное давление после штуцера: {after!r}")
        add(current, 8, match[1], "p_well_after_choke", "атм", exported, "snapshot", "current")

    monthly = book.sheet_by_name("Динамика")
    _check_headers(
        monthly,
        2,
        {
            0: "мес,год",
            1: "Qжид.",
            5: "Р уст.",
            6: "Р бг.",
            7: "Р пл.",
            8: "Р заб.",
            10: "Жид-ть м3/сут",
            11: "Закачка",
            12: "Траб",
            13: "Тпрост",
            14: "Тогр",
            15: "Р уст.",
        },
    )
    _check_headers(
        monthly,
        3,
        {1: "м3/сут", 10: "м3/сут", 11: "м3/мес", 12: "ч/мес", 13: "ч/мес", 14: "ч/мес", 15: "атм"},
    )
    for row in range(4, monthly.nrows):
        period = str(monthly.cell_value(row, 0)).strip()
        if not period:
            continue
        observed = datetime.strptime(period, "%m.%Y").date().isoformat()
        for column, (metric, unit, kind) in _MONTHLY.items():
            add(
                monthly, row, monthly.cell_value(row, column), metric, unit, observed, "month", kind
            )

    study = book.sheet_by_name("ГДИ")
    _check_headers(
        study, 1, {1: "Дата исследования", 2: "Вид исслед.", 3: "Р уст", 4: "Рзаб/ Рпл."}
    )
    _check_headers(study, 3, {3: "атм", 4: "атм", 8: "м3/сут", 9: "г/см3"})
    for row in range(4, study.nrows):
        raw_date = study.cell_value(row, 1)
        if not str(raw_date).strip():
            continue
        observed = xlrd.xldate_as_datetime(raw_date, book.datemode).date().isoformat()
        kind = str(study.cell_value(row, 2)).strip()
        pressure = {"Р заб": "p_bottomhole", "Р пл": "p_reservoir"}.get(kind, "p_study")
        for column, metric, unit in [
            (3, "p_well", "атм"),
            (4, pressure, "атм"),
            (8, "flow_m3_day", "м³/сут"),
            (9, "density_kgm3", "кг/м³"),
        ]:
            add(
                study,
                row,
                study.cell_value(row, column),
                metric,
                unit,
                observed,
                "day",
                "study",
                kind,
            )
    return records


def read_armits_wells(path: Path) -> list[dict[str, Any]]:
    """Read supported exports; reject unknown folders/layouts or invalid measurements."""
    records = []
    with ZipFile(path) as archive:
        entries = [
            info
            for info in archive.infolist()
            if not info.is_dir() and info.filename.lower().endswith(".xls")
        ]
        if not entries or len(entries) > 1000 or sum(e.file_size for e in entries) > 100_000_000:
            raise ValueError("ZIP: требуется 1–1000 XLS файлов общим размером до 100 МБ")
        for entry in entries:
            decoded_name = _decoded(entry).replace("\\", "/")
            folders = [part for part in decoded_name.split("/") if part in _PLANTS]
            if len(folders) != 1:
                raise ValueError(f"{entry.filename}: неизвестный объект")
            book = xlrd.open_workbook(file_contents=archive.read(entry))
            try:
                records.extend(_read_workbook(book, decoded_name, _PLANTS[folders[0]]))
            finally:
                if hasattr(book, "release_resources"):
                    book.release_resources()
    return records


_FILE = re.compile(r"inf_skw(.+)\.xls$", re.IGNORECASE)
_MONTH = re.compile(r"^(\d{2})\.(\d{4})$")

# Колонки листа «Динамика» (строки данных начинаются после трёх строк шапки).
_DYN = {
    "q": 1,
    "choke": 4,
    "p_head": 5,
    "p_bg": 6,
    "p_res": 7,
    "p_bottom": 8,
    "injectivity": 9,
    "volume": 11,
    "hours_work": 12,
    "hours_idle": 13,
}


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


@dataclass(frozen=True)
class MonthRecord:
    """Строка помесячной истории скважины."""

    month: date
    q_m3_day: float | None
    choke_mm: float | None
    p_head_atm: float | None
    p_bg_atm: float | None
    p_reservoir_atm: float | None
    p_bottom_atm: float | None
    injectivity: float | None
    volume_m3: float | None
    hours_work: float | None
    hours_idle: float | None

    @property
    def calendar_hours(self) -> float:
        return 24.0 * calendar.monthrange(self.month.year, self.month.month)[1]

    @property
    def rate_m3h(self) -> float | None:
        """Средний расход в часы работы: объём за месяц / время работы."""
        if not self.volume_m3 or not self.hours_work:
            return None
        return self.volume_m3 / self.hours_work

    @property
    def mean_rate_m3h(self) -> float | None:
        """Среднекалендарный расход: объём за месяц / часы месяца.

        Для расчёта трения в общих водоводах берётся именно он: скважины,
        работающие циклически, не качают одновременно весь месяц.
        """
        if not self.volume_m3:
            return None
        return self.volume_m3 / self.calendar_hours


@dataclass
class WellCard:
    """Карточка нагнетательной скважины."""

    well: str
    state: str
    q_m3_day: float | None
    p_before_choke_atm: float | None
    p_after_choke_atm: float | None
    current: MonthRecord | None
    months: list[MonthRecord] = field(default_factory=list)

    @property
    def operating(self) -> bool:
        return self.state.lower().startswith("действ")

    @property
    def last_month(self) -> MonthRecord | None:
        return self.months[-1] if self.months else None

    def annual_volume_m3(self, months: int = 12) -> float:
        """Объём закачки за последние полные месяцы, м³."""
        return sum(record.volume_m3 or 0.0 for record in self.months[-months:])

    def annual_hours(self, months: int = 12) -> float:
        """Время работы за последние полные месяцы, ч."""
        return sum(record.hours_work or 0.0 for record in self.months[-months:])


def _month(value: object) -> date | None:
    match = _MONTH.match(str(value).strip())
    if not match:
        return None
    return date(int(match.group(2)), int(match.group(1)), 1)


def _cell(sheet, row: int, column: int) -> object:
    if row >= sheet.nrows or column >= sheet.ncols:
        return ""
    return sheet.cell_value(row, column)


def parse_card(content: bytes, file_code: str) -> WellCard:
    """Разобрать один файл карточки скважины (формат .xls)."""
    import xlrd

    book = xlrd.open_workbook(file_contents=content)
    regime = book.sheet_by_name("Режим")
    dynamics = book.sheet_by_name("Динамика")

    rows: list[MonthRecord] = []
    for row in range(3, dynamics.nrows):
        month = _month(_cell(dynamics, row, 0))
        if month is None:
            continue
        value = {key: _number(_cell(dynamics, row, column)) for key, column in _DYN.items()}
        rows.append(
            MonthRecord(
                month=month,
                q_m3_day=value["q"],
                choke_mm=value["choke"],
                p_head_atm=value["p_head"],
                p_bg_atm=value["p_bg"],
                p_reservoir_atm=value["p_res"],
                p_bottom_atm=value["p_bottom"],
                injectivity=value["injectivity"],
                volume_m3=value["volume"],
                hours_work=value["hours_work"],
                hours_idle=value["hours_idle"],
            )
        )
    # Первая строка — текущий неполный месяц, далее история. В истории иногда
    # повторно встречается текущий месяц; полными считаются только месяцы до него.
    current = rows[0] if rows else None
    history = sorted(
        (record for record in rows[1:] if current is None or record.month < current.month),
        key=lambda record: record.month,
    )

    return WellCard(
        well=well_from_file_code(file_code),
        state=str(_cell(regime, 4, 1)).strip(),
        q_m3_day=_number(_cell(regime, 8, 1)),
        p_before_choke_atm=_number(_cell(regime, 8, 4)) or None,
        p_after_choke_atm=_number(_cell(regime, 8, 6)) or None,
        current=current,
        months=history,
    )


def _decoded(info: zipfile.ZipInfo) -> str:
    """Имя файла в архиве: без флага UTF-8 Windows-архиватор пишет cp866."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp866")
    except UnicodeError:
        return info.filename


def read_cards(archive: Path, folder: str) -> list[WellCard]:
    """Карточки скважин одной КНС из архива выгрузки.

    ``folder`` — имя папки станции в архиве или его начало («54», «ОПУ»).
    """
    cards: list[WellCard] = []
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if info.is_dir():
                continue
            parts = _decoded(info).replace("\\", "/").split("/")
            if len(parts) < 2 or not parts[-2].startswith(folder):
                continue
            match = _FILE.search(parts[-1])
            if not match:
                continue
            cards.append(parse_card(bundle.read(info), match.group(1)))
    return sorted(cards, key=lambda card: card.well)


def main() -> None:
    import argparse
    import json
    from collections import Counter

    from ..config import project_root
    from ..db import default_database_path
    from ..db_seed import bootstrap_database

    parser = argparse.ArgumentParser(description="Импорт истории скважин АРМИТС из ZIP")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--database", type=Path, default=default_database_path())
    args = parser.parse_args()
    rows = read_armits_wells(args.archive)
    database = bootstrap_database(args.database, project_root() / "config/plants")
    database.add_well_measurements(rows)
    print(
        json.dumps(
            {"records": len(rows), "objects": Counter(row["plant_code"] for row in rows)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
