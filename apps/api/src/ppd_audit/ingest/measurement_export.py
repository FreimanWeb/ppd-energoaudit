"""Годовые выгрузки «Измерения» АСУ ТП (xls) в поток точек SCADA.

Формат: один лист, в первых строках заголовок «Измерения», имя точки учёта
(«Аз КНС 54. НА 1»), период («С 25.10.2025 00:00:00 по 25.10.2026 00:00:00»),
затем строка шапки «Дата | <параметр> | Кач. | …». В конце файлов расхода и
мощности — итоговые строки «Итого:», «Всего:», «Пустых:».

Каждая колонка переводится в тег той же модели, что и выгрузки ТИ/ТС
(``config/scada_tags.yaml``), поэтому дальше работает общий конвейер:
ступенчатые сигналы давлений, суточные суммы расхода и энергии, наработка,
мощность по энергии за интервал.

- «Давление на выкиде / на приёме / в коллекторе» — POUNA / PINNA / PKOL_.
- «Расход на выкиде» — объём за интервал опроса, м³ (QVD__#I3).
  Колонка «Мгновенный расход» — тот же ряд в м³/ч, она не читается.
- «Акт.прямая мощность, кВт» — средняя мощность интервала; в модель идёт
  энергия за интервал P·T (APWCN#I3), из которой восстанавливаются мощность,
  суточная энергия и наработка.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from .scada_txt import ScadaPoint, ScadaTag, parse_timestamp


HEADER_ROW = "Дата"
QUALITY_COLUMN = "Кач."
_PERIOD = re.compile(
    r"С\s+(\d{2}\.\d{2}\.\d{4}(?: [\d:]+)?)\s+по\s+(\d{2}\.\d{2}\.\d{4}(?: [\d:]+)?)"
)


@dataclass(frozen=True)
class ColumnRule:
    """Как колонка выгрузки превращается в тег модели."""

    code: str
    integral: bool = False
    energy_from_power: bool = False


# Порядок важен: «мгновенный расход» проверяется раньше, чем «расход».
COLUMN_RULES: tuple[tuple[str, ColumnRule | None], ...] = (
    ("мгн", None),
    ("мгновенный", None),
    ("давление на выкиде", ColumnRule("POUNA")),
    ("давление на приёме", ColumnRule("PINNA")),
    ("давление на приеме", ColumnRule("PINNA")),
    ("давление в коллекторе", ColumnRule("PKOL_")),
    ("расход на выкиде", ColumnRule("QVD__", integral=True)),
    ("мощность", ColumnRule("APWCN", integral=True, energy_from_power=True)),
)


@dataclass(frozen=True)
class ExportSheet:
    """Разобранный файл выгрузки."""

    source: str  # путь внутри архива или имя файла
    point_title: str
    start: datetime | None
    end: datetime | None
    points: list[ScadaPoint]


def column_rule(header: str) -> ColumnRule | None:
    text = " ".join(str(header).lower().split())
    for marker, rule in COLUMN_RULES:
        if marker in text:
            return rule
    return None


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ".").strip())
    except ValueError:
        return None


def _timestamp(value: object, datemode: int) -> datetime | None:
    if isinstance(value, float):
        import xlrd

        try:
            return xlrd.xldate_as_datetime(value, datemode)
        except Exception:
            return None
    return parse_timestamp(str(value))


def parse_export(
    content: bytes,
    source: str,
    targets: dict[str, tuple[str, str]],
    interval_hours: float,
) -> ExportSheet | None:
    """Точки одного xls; None, если точка учёта не описана в ``targets``.

    ``targets`` — «имя точки учёта» → (код объекта, блок), например
    ``"Аз КНС 54. НА 1": ("5401", "PUMP_001")``.
    """
    import xlrd

    book = xlrd.open_workbook(file_contents=content)
    sheet = book.sheet_by_index(0)
    header_index = None
    title = ""
    start = end = None
    for row in range(min(sheet.nrows, 12)):
        first = str(sheet.cell_value(row, 0)).strip()
        if first == HEADER_ROW:
            header_index = row
            break
        match = _PERIOD.search(first)
        if match:
            start, end = (parse_timestamp(item) for item in match.groups())
        elif first and first != "Измерения" and first != "Расход" and not title:
            title = first
    if header_index is None:
        raise ValueError(f"{source}: нет строки шапки «{HEADER_ROW}»")
    target = targets.get(" ".join(title.split()))
    if target is None:
        return None
    object_code, unit = target

    headers = [str(value).strip() for value in sheet.row_values(header_index)]
    columns: list[tuple[int, int | None, ColumnRule]] = []
    for index, header in enumerate(headers[1:], start=1):
        if not header or header == QUALITY_COLUMN:
            continue
        rule = column_rule(header)
        if rule is None:
            continue
        quality = (
            index + 1 if index + 1 < len(headers) and headers[index + 1] == QUALITY_COLUMN else None
        )
        columns.append((index, quality, rule))

    points: list[ScadaPoint] = []
    for row in range(header_index + 1, sheet.nrows):
        values = sheet.row_values(row)
        timestamp = _timestamp(values[0], book.datemode)
        if timestamp is None:
            continue  # «Итого:», «Всего:», «Пустых:»
        for index, quality, rule in columns:
            value = _number(values[index]) if index < len(values) else None
            if value is None:
                continue
            if quality is not None:
                flag = _number(values[quality]) if quality < len(values) else None
                if flag not in (None, 0.0):
                    continue  # недостоверное значение по признаку качества
            if rule.energy_from_power:
                value *= interval_hours
            tag = ScadaTag(object_code, unit, rule.code, rule.integral)
            points.append(ScadaPoint(tag, timestamp, value))
    return ExportSheet(source, title, start, end, points)


def export_files(root: Path) -> list[Path]:
    """Архивы и файлы годовых выгрузок в каталоге."""
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".zip", ".xls"}
        and not path.name.startswith("~$")
    )


def _member_name(info: zipfile.ZipInfo) -> str:
    """Имя файла в архиве: архиваторы Windows пишут его в cp866 без флага UTF-8."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp866")
    except UnicodeError:
        return info.filename


def iter_export_contents(path: Path) -> Iterator[tuple[str, bytes]]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                name = _member_name(info)
                if info.is_dir() or not name.lower().endswith(".xls"):
                    continue
                yield str(PurePosixPath(path.name, name)), archive.read(info)
    else:
        yield path.name, path.read_bytes()


def read_exports(
    path: Path, targets: dict[str, tuple[str, str]], interval_hours: float
) -> tuple[list[ExportSheet], list[str]]:
    """Все листы выгрузки из файла; второй элемент — нераспознанные файлы."""
    sheets: list[ExportSheet] = []
    skipped: list[str] = []
    for name, content in iter_export_contents(path):
        try:
            sheet = parse_export(io.BytesIO(content).getvalue(), name, targets, interval_hours)
        except Exception:
            skipped.append(name)
            continue
        if sheet is None:
            skipped.append(name)
        else:
            sheets.append(sheet)
    return sheets, skipped
