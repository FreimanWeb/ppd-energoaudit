"""Разбор выгрузок АСУ ТП (ТИ/ТС) в canonical-телеметрию.

Формат выгрузки — CSV в кодировке cp1251 с запятой и как разделителем полей,
и как десятичным разделителем. Строка ТИ::

    KNS__#0197#PUMP_#003#APWCN#I3,01.07.2025 0:30:00,176,64

то есть значение «176,64» занимает два последних поля и склеивается обратно.
Строка ТС::

    KNS__#0197#PUMP_#003#NAON_,НОРМ,ТС,1,01.07.2025 10:29:31,Работа,…

Смысл тегов задаётся в ``config/scada_tags.yaml``, а не зашит в коде: для
нового объекта достаточно дописать туда его код и агрегаты.

Что получается на выходе:

* мгновенные значения (давления, мощность) — как ступенчатый сигнал, в БД
  пишутся только изменения: у мощности это 285 000 точек против 5 700;
* накопления за интервал (расход, активная энергия) — суммой за сутки, с
  меткой на начало суток, как их ждёт ``services.telemetry_audit``;
* наработка за сутки — из числа интервалов с ненулевым расходом;
* состояние НА из ТС — как метрика ``pump_state``.
"""

from __future__ import annotations

import io
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


ENCODING = "cp1251"
INTEGRAL_SUFFIX = "I3"
MEASUREMENT_HEADER = "ЗНАЧЕНИЕ_ИЗМЕРЕНИЯ"
SIGNAL_HEADER = "ЗНАЧЕНИЕ_СИГНАЛА"
_TIMESTAMP_FORMATS = ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y")


class ScadaFormatError(ValueError):
    """Файл не похож на выгрузку ТИ/ТС."""


@dataclass(frozen=True)
class ScadaTag:
    object_code: str  # 0197
    unit: str  # PUMP_001
    code: str  # APWCN
    integral: bool  # был суффикс #I3


@dataclass(frozen=True)
class ScadaPoint:
    tag: ScadaTag
    timestamp: datetime
    value: float


@dataclass
class ScadaMapping:
    """Разобранный ``config/scada_tags.yaml``."""

    interval_hours: float
    objects: dict[str, dict[str, Any]]
    points: dict[str, dict[str, str]]
    station_points: dict[str, dict[str, str]]
    interval_sums: dict[str, dict[str, Any]]
    runtime: dict[str, str]
    states: dict[str, dict[str, str]]

    @classmethod
    def from_yaml(cls, path: Path) -> ScadaMapping:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            interval_hours=float(raw.get("interval_hours") or 0.5),
            objects=raw.get("objects") or {},
            points=raw.get("points") or {},
            station_points=raw.get("station_points") or {},
            interval_sums=raw.get("interval_sums") or {},
            runtime=raw.get("runtime") or {},
            states=raw.get("states") or {},
        )

    def target(self, tag: ScadaTag) -> tuple[str, str] | None:
        """(plant_code, technical_place) или None, если объект не описан."""
        obj = self.objects.get(tag.object_code)
        if not obj:
            return None
        return obj["plant"], obj.get("technical_place", "main")

    def aggregate(self, tag: ScadaTag) -> str | None:
        obj = self.objects.get(tag.object_code) or {}
        return (obj.get("aggregates") or {}).get(tag.unit)

    @property
    def runtime_codes(self) -> set[str]:
        return {
            code for code, spec in self.interval_sums.items() if spec.get("runtime_source")
        }


@dataclass
class DailyTotals:
    sums: dict[str, float] = field(default_factory=dict)
    runtime_intervals: set[datetime] = field(default_factory=set)
    intervals: set[datetime] = field(default_factory=set)


def parse_tag(raw: str) -> ScadaTag | None:
    """`KNS__#0197#PUMP_#003#APWCN#I3` → ScadaTag; None, если форма чужая."""
    parts = raw.strip().split("#")
    if len(parts) < 5:
        return None
    object_code, block, index, code = parts[1], parts[2], parts[3], parts[4]
    integral = len(parts) > 5 and parts[5].strip().upper() == INTEGRAL_SUFFIX
    return ScadaTag(object_code, f"{block}{index}", code, integral)


def parse_timestamp(raw: str) -> datetime | None:
    text = raw.strip()
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_decimal(fields: list[str]) -> float | None:
    """Склеить значение, разрезанное десятичной запятой: ['176','64'] → 176.64."""
    text = ".".join(part.strip() for part in fields if part.strip() != "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def iter_measurements(lines: Iterator[str]) -> Iterator[ScadaPoint]:
    """Разобрать выгрузку ТИ: тег, дата, значение."""
    for line in lines:
        fields = line.rstrip("\r\n").split(",")
        if len(fields) < 3:
            continue
        tag = parse_tag(fields[0])
        timestamp = parse_timestamp(fields[1])
        value = parse_decimal(fields[2:])
        if tag is None or timestamp is None or value is None:
            continue
        yield ScadaPoint(tag, timestamp, value)


def iter_signals(lines: Iterator[str]) -> Iterator[ScadaPoint]:
    """Разобрать выгрузку ТС: тег, признак, источник, значение, дата, текст…

    Поля после даты содержат запятые внутри текста события, поэтому читаются
    только фиксированные позиции слева.
    """
    for line in lines:
        fields = line.rstrip("\r\n").split(",")
        if len(fields) < 5:
            continue
        tag = parse_tag(fields[0])
        timestamp = parse_timestamp(fields[4])
        value = parse_decimal([fields[3]])
        if tag is None or timestamp is None or value is None:
            continue
        yield ScadaPoint(tag, timestamp, value)


def iter_points(text: Iterator[str]) -> Iterator[ScadaPoint]:
    """Определить тип выгрузки по шапке и разобрать её."""
    header = next(text, "")
    if MEASUREMENT_HEADER in header:
        yield from iter_measurements(text)
    elif SIGNAL_HEADER in header:
        yield from iter_signals(text)
    else:
        raise ScadaFormatError(f"неизвестная шапка выгрузки: {header.strip()[:80]}")


def scada_files(root: Path) -> list[Path]:
    """Выгрузки в каталоге: .zip с текстом внутри или сами .txt."""
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".zip", ".txt"}
        and not path.name.startswith("~$")
    )


def read_points(path: Path) -> Iterator[ScadaPoint]:
    """Точки из одного файла — .txt напрямую или все .txt внутри .zip."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".txt"):
                    continue
                stream = io.TextIOWrapper(
                    io.BytesIO(archive.read(info)), encoding=ENCODING, errors="replace"
                )
                yield from iter_points(stream)
    else:
        with path.open("r", encoding=ENCODING, errors="replace") as stream:
            yield from iter_points(stream)


@dataclass(frozen=True)
class CanonicalRow:
    """Готовая к записи в БД строка телеметрии."""

    plant_code: str
    aggregate_code: str | None
    technical_place_code: str
    timestamp: datetime
    metric: str
    value: float
    unit: str
    source_tag: str


def build_rows(points: Iterator[ScadaPoint], mapping: ScadaMapping) -> list[CanonicalRow]:
    """Свести поток точек к строкам canonical-телеметрии."""
    rows: list[CanonicalRow] = []
    last_value: dict[tuple, float] = {}
    daily: dict[tuple, DailyTotals] = defaultdict(DailyTotals)
    direct_power: set[tuple] = set()
    derived_power: dict[tuple, list[tuple[datetime, float, ScadaTag]]] = defaultdict(list)

    for point in points:
        target = mapping.target(point.tag)
        if target is None:
            continue
        plant, place = target
        aggregate = mapping.aggregate(point.tag)
        code = point.tag.code

        spec = mapping.interval_sums.get(code)
        if spec is not None and aggregate is not None:
            if spec.get("integral") and not point.tag.integral:
                continue  # счётчик с начала эксплуатации, а не расход за интервал
            key = (plant, place, aggregate, point.timestamp.date())
            totals = daily[key]
            metric = spec["metric"]
            totals.sums[metric] = totals.sums.get(metric, 0.0) + point.value
            totals.intervals.add(point.timestamp)
            if code in mapping.runtime_codes and point.value > 0:
                totals.runtime_intervals.add(point.timestamp)
            power_spec = spec.get("derive_power")
            if power_spec and mapping.interval_hours > 0:
                derived_power[(plant, place, aggregate)].append(
                    (point.timestamp, point.value / mapping.interval_hours, point.tag)
                )
            continue

        spec = mapping.points.get(code) or mapping.states.get(code)
        if spec is not None and aggregate is not None:
            if spec["metric"] == "power":
                direct_power.add((plant, place, aggregate))
            rows.extend(
                _step_row(
                    last_value, plant, aggregate, place, point, spec, point.tag
                )
            )
            continue

        spec = mapping.station_points.get(code)
        if spec is not None:
            rows.extend(
                _step_row(last_value, plant, None, place, point, spec, point.tag)
            )

    rows.extend(_derived_power_rows(derived_power, direct_power, last_value, mapping))
    rows.extend(_daily_rows(daily, mapping))
    rows.sort(key=lambda row: (row.timestamp, row.metric, row.aggregate_code or ""))
    return rows


def _step_row(
    last_value: dict[tuple, float],
    plant: str,
    aggregate: str | None,
    place: str,
    point: ScadaPoint,
    spec: dict[str, str],
    tag: ScadaTag,
) -> list[CanonicalRow]:
    """Ступенчатый сигнал: строка пишется только при изменении значения."""
    metric = spec["metric"]
    key = (plant, place, aggregate, metric)
    if last_value.get(key) == point.value:
        return []
    last_value[key] = point.value
    return [
        CanonicalRow(
            plant_code=plant,
            aggregate_code=aggregate,
            technical_place_code=place,
            timestamp=point.timestamp,
            metric=metric,
            value=point.value,
            unit=spec.get("unit", ""),
            source_tag=f"{tag.object_code}#{tag.unit}#{tag.code}",
        )
    ]


def _derived_power_rows(
    derived: dict[tuple, list[tuple[datetime, float, ScadaTag]]],
    direct: set[tuple],
    last_value: dict[tuple, float],
    mapping: ScadaMapping,
) -> list[CanonicalRow]:
    """Мощность из энергии за интервал — только там, где нет своего датчика.

    Без ряда мощности расчётное ядро не может выбрать давления «в момент
    положительной мощности» и отказывается строить режим, хотя энергия за
    интервал измерена. P = W/T — это формула (12) методики, а не догадка.
    """
    spec = next(
        (
            item["derive_power"]
            for item in mapping.interval_sums.values()
            if isinstance(item, dict) and item.get("derive_power")
        ),
        None,
    )
    if spec is None:
        return []

    rows: list[CanonicalRow] = []
    for unit, samples in derived.items():
        if unit in direct:
            continue
        plant, place, aggregate = unit
        for timestamp, value, tag in sorted(samples, key=lambda item: item[0]):
            key = (plant, place, aggregate, spec["metric"])
            rounded = round(value, 3)
            if last_value.get(key) == rounded:
                continue
            last_value[key] = rounded
            rows.append(
                CanonicalRow(
                    plant_code=plant,
                    aggregate_code=aggregate,
                    technical_place_code=place,
                    timestamp=timestamp,
                    metric=spec["metric"],
                    value=rounded,
                    unit=spec.get("unit", "кВт"),
                    source_tag=f"{tag.code} / {mapping.interval_hours} ч",
                )
            )
    return rows


def truncated_days(daily: dict[tuple, DailyTotals], interval_hours: float) -> set[tuple]:
    """Последние сутки агрегата, если выгрузка обрывается до конца дня.

    Такие сутки нельзя выдавать за суточные итоги: Q_сут и W_сут покроют
    половину дня, а восстановленный ряд мощности — все 24 часа, и сверка
    честно объявит режим непригодным.

    Правило срабатывает только там, где в выгрузке есть хотя бы одни полные
    сутки: тогда короткий последний день — артефакт границы экспорта. Если
    полных суток нет вовсе (выгрузили несколько часов), это и есть заказанное
    окно, и отбирать у него итоги не за что. Пропуски интервалов в середине
    периода обрывом не считаются — там значение держится до следующего.
    """
    slots_per_day = 24.0 / interval_hours if interval_hours > 0 else 0
    last_by_unit: dict[tuple, datetime] = {}
    has_full_day: set[tuple] = set()
    for (plant, place, aggregate, day), totals in daily.items():
        if not totals.intervals:
            continue
        unit = (plant, place, aggregate)
        newest = max(totals.intervals)
        if unit not in last_by_unit or newest > last_by_unit[unit]:
            last_by_unit[unit] = newest
        day_end = datetime.combine(day, datetime.min.time()) + timedelta(days=1)
        if newest + timedelta(hours=interval_hours) >= day_end and (
            len(totals.intervals) >= slots_per_day
        ):
            has_full_day.add(unit)

    truncated = set()
    for unit, newest in last_by_unit.items():
        if unit not in has_full_day:
            continue
        day_end = datetime.combine(newest.date(), datetime.min.time()) + timedelta(days=1)
        if newest + timedelta(hours=interval_hours) < day_end:
            truncated.add((*unit, newest.date()))
    return truncated


def _daily_rows(daily: dict[tuple, DailyTotals], mapping: ScadaMapping) -> list[CanonicalRow]:
    rows: list[CanonicalRow] = []
    runtime_spec = mapping.runtime
    incomplete = truncated_days(daily, mapping.interval_hours)
    for (plant, place, aggregate, day), totals in daily.items():
        if (plant, place, aggregate, day) in incomplete:
            continue
        timestamp = datetime.combine(day, datetime.min.time())
        for code, spec in mapping.interval_sums.items():
            metric = spec["metric"]
            if metric not in totals.sums:
                continue
            rows.append(
                CanonicalRow(
                    plant_code=plant,
                    aggregate_code=aggregate,
                    technical_place_code=place,
                    timestamp=timestamp,
                    metric=metric,
                    value=round(totals.sums[metric], 3),
                    unit=spec.get("unit", ""),
                    source_tag=f"{code} (сумма за сутки)",
                )
            )
        if runtime_spec and totals.runtime_intervals:
            hours = min(24.0, len(totals.runtime_intervals) * mapping.interval_hours)
            rows.append(
                CanonicalRow(
                    plant_code=plant,
                    aggregate_code=aggregate,
                    technical_place_code=place,
                    timestamp=timestamp,
                    metric=runtime_spec.get("metric", "runtime"),
                    value=round(hours, 3),
                    unit=runtime_spec.get("unit", "ч"),
                    source_tag="интервалы с ненулевым расходом",
                )
            )
    return rows


def read_rows(path: Path, mapping: ScadaMapping) -> list[CanonicalRow]:
    return build_rows(read_points(path), mapping)


def day_bounds(rows: list[CanonicalRow]) -> tuple[datetime, datetime] | None:
    if not rows:
        return None
    stamps = [row.timestamp for row in rows]
    return min(stamps), max(stamps) + timedelta(days=1)
