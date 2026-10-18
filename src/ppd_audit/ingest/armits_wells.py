"""Read well measurements from ARMIТС XLS exports without extracting the ZIP.

Pressures retain the source unit «атм»; monthly rows are not daily telemetry.
The current snapshot date is the export date, not a proven measurement date.
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import xlrd


_PLANTS = {
    '54 Азнакаевскнефть': 'kns54an',
    '97-2 Елховнефть': 'kns97pren',
    'ОПУ Джалильнефть': 'knsopu',
}
_MONTHLY = {
    1: ('flow_m3_day', 'м³/сут', 'monthly_actual'),
    5: ('p_well', 'атм', 'monthly_actual'),
    6: ('p_bg', 'атм', 'monthly_actual'),
    7: ('p_reservoir', 'атм', 'monthly_actual'),
    8: ('p_bottomhole', 'атм', 'monthly_actual'),
    10: ('flow_m3_day', 'м³/сут', 'monthly_reported'),
    11: ('injection_volume_m3', 'м³', 'monthly_reported'),
    12: ('runtime_hours', 'ч', 'monthly_reported'),
    13: ('downtime_hours', 'ч', 'monthly_reported'),
    14: ('restricted_hours', 'ч', 'monthly_reported'),
    15: ('p_well', 'атм', 'monthly_reported'),
}


def _check_headers(sheet: Any, row: int, expected: dict[int, str]) -> None:
    for column, value in expected.items():
        if sheet.nrows <= row or sheet.ncols <= column or str(
            sheet.cell_value(row, column)
        ).strip() != value:
            raise ValueError(f'{sheet.name}: неизвестный заголовок, строка {row + 1}')


def _number(value: Any, location: str) -> float | None:
    if value is None or str(value).strip() == '':
        return None
    try:
        number = float(str(value).strip().replace(',', '.'))
    except ValueError as exc:
        raise ValueError(f'{location}: не число {value!r}') from exc
    if isinstance(value, bool) or not math.isfinite(number) or number < 0:
        raise ValueError(f'{location}: требуется конечное неотрицательное число: {value!r}')
    return number


def _read_workbook(book: Any, source_file: str, plant: str) -> list[dict[str, Any]]:
    current = book.sheet_by_name('Режим')
    header = str(current.cell_value(0, 0))
    identity = re.search(r'СКВАЖИ[HН]Е\s+(\S+).*?на\s+(\d{2}/\d{2}/\d{4})', header)
    if not identity:
        raise ValueError(f'{source_file}: неизвестный номер скважины/дата выгрузки')
    well, exported = identity.groups()
    exported = datetime.strptime(exported, '%d/%m/%Y').date().isoformat()
    base = {'plant_code': plant, 'well_code': well, 'source_file': source_file,
            'exported_at': exported}
    records = []

    def add(sheet, row, value, metric, unit, observed, grain, kind, study_type=''):
        location = f'{source_file}, {sheet.name}, строка {row + 1}'
        number = _number(value, location)
        if number is not None:
            if metric == 'density_kgm3':
                number *= 1000
            records.append({**base, 'observed_at': observed, 'grain': grain,
                            'record_kind': kind, 'metric': metric, 'value': number,
                            'unit': unit, 'study_type': study_type, 'source_sheet': sheet.name,
                            'source_row': row + 1})

    _check_headers(current, 8, {0: 'Qжид.факт', 2: 'м3/сут', 3: 'Ру до шт.', 5: 'атм'})
    add(current, 8, current.cell_value(8, 1), 'flow_m3_day', 'м³/сут',
        exported, 'snapshot', 'current')
    add(current, 8, current.cell_value(8, 4), 'p_well_before_choke', 'атм',
        exported, 'snapshot', 'current')
    after = str(current.cell_value(8, 6)).strip()
    if after:
        match = re.fullmatch(r'после\s+(.+)', after)
        if not match:
            raise ValueError(f'{source_file}: неизвестное давление после штуцера: {after!r}')
        add(current, 8, match[1], 'p_well_after_choke', 'атм', exported, 'snapshot', 'current')

    monthly = book.sheet_by_name('Динамика')
    _check_headers(monthly, 2, {0: 'мес,год', 1: 'Qжид.', 5: 'Р уст.', 6: 'Р бг.',
                               7: 'Р пл.', 8: 'Р заб.', 10: 'Жид-ть м3/сут',
                               11: 'Закачка', 12: 'Траб', 13: 'Тпрост', 14: 'Тогр',
                               15: 'Р уст.'})
    _check_headers(monthly, 3, {1: 'м3/сут', 10: 'м3/сут', 11: 'м3/мес',
                               12: 'ч/мес', 13: 'ч/мес', 14: 'ч/мес', 15: 'атм'})
    for row in range(4, monthly.nrows):
        period = str(monthly.cell_value(row, 0)).strip()
        if not period:
            continue
        observed = datetime.strptime(period, '%m.%Y').date().isoformat()
        for column, (metric, unit, kind) in _MONTHLY.items():
            add(monthly, row, monthly.cell_value(row, column), metric, unit,
                observed, 'month', kind)

    study = book.sheet_by_name('ГДИ')
    _check_headers(study, 1, {1: 'Дата исследования', 2: 'Вид исслед.', 3: 'Р уст',
                             4: 'Рзаб/ Рпл.'})
    _check_headers(study, 3, {3: 'атм', 4: 'атм', 8: 'м3/сут', 9: 'г/см3'})
    for row in range(4, study.nrows):
        raw_date = study.cell_value(row, 1)
        if not str(raw_date).strip():
            continue
        observed = xlrd.xldate_as_datetime(raw_date, book.datemode).date().isoformat()
        kind = str(study.cell_value(row, 2)).strip()
        pressure = {'Р заб': 'p_bottomhole', 'Р пл': 'p_reservoir'}.get(kind, 'p_study')
        for column, metric, unit in [(3, 'p_well', 'атм'), (4, pressure, 'атм'),
                                     (8, 'flow_m3_day', 'м³/сут'),
                                     (9, 'density_kgm3', 'кг/м³')]:
            add(study, row, study.cell_value(row, column), metric, unit,
                observed, 'day', 'study', kind)
    return records


def read_armits_wells(path: Path) -> list[dict[str, Any]]:
    """Read supported exports; reject unknown folders/layouts or invalid measurements."""
    records = []
    with ZipFile(path) as archive:
        entries = [info for info in archive.infolist()
                   if not info.is_dir() and info.filename.lower().endswith('.xls')]
        if not entries or len(entries) > 1000 or sum(e.file_size for e in entries) > 100_000_000:
            raise ValueError('ZIP: требуется 1–1000 XLS файлов общим размером до 100 МБ')
        for entry in entries:
            folders = [part for part in entry.filename.split('/') if part in _PLANTS]
            if len(folders) != 1:
                raise ValueError(f'{entry.filename}: неизвестный объект')
            book = xlrd.open_workbook(file_contents=archive.read(entry))
            try:
                records.extend(_read_workbook(book, entry.filename, _PLANTS[folders[0]]))
            finally:
                if hasattr(book, 'release_resources'):
                    book.release_resources()
    return records


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
    print(json.dumps({"records": len(rows), "objects": Counter(
        row["plant_code"] for row in rows
    )}, ensure_ascii=False))


if __name__ == "__main__":
    main()
