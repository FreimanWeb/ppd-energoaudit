"""Чтение выгрузок CRM-прогноза подачи по агрегатам.

Сама модель (ARX/CRM с учётом событий пуска-останова) обучается и считается
внешним инструментом — по одной модели на объект. Сюда попадают только её
выгрузки: таблица прогноза с шагом опроса. Дашборд сводит их с фактом из БД.

Раскладка в репозитории::

    data/crm/<объект>/model_metadata.json   паспорт модели (необязательно)
    data/crm/<объект>/<прогон>/forecast_by_equipment_and_total.csv
    data/crm/<объект>/<прогон>/run.json     подпись прогона (необязательно)

Имена файлов внутри прогона — те же, что выдаёт пайплайн, чтобы папку с
новым прогоном можно было положить как есть, ничего не переименовывая.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator, Mapping


CRM_DIRNAME = "crm"

# Пайплайн кладёт полную таблицу и сокращённую (только прогноз по агрегатам
# и сумма). Полная предпочтительнее: в ней те же столбцы плюс входы модели.
FORECAST_FILES = ("multioutput_forecast.csv", "forecast_by_equipment_and_total.csv")

METADATA_FILE = "model_metadata.json"
RUN_FILE = "run.json"
EVENTS_FILE = "event_scenario_summary.csv"

# PRED::PUMP_001_QVD_I3 — прогноз подачи агрегата за интервал опроса.
# BASE:: — тот же ряд без учёта событий, он берётся отдельным прогоном.
PUMP_COLUMN = re.compile(r"^PRED::(?P<unit>[A-Z]+_\d+)_QVD_I3$")
TOTAL_COLUMN = "Q_OUT_SUM"

TIMESTAMP_COLUMN = "datetime"
TIMESTAMP_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M:%S")

DEFAULT_INTERVAL_HOURS = 0.5


class CrmForecastError(ValueError):
    """Выгрузка прогноза не читается."""


@dataclass(frozen=True)
class ForecastRun:
    """Один прогон прогноза: папка, подпись и паспорт модели."""

    path: Path
    code: str
    title: str
    events: bool
    object_id: str | None = None
    model: str | None = None

    @property
    def table(self) -> Path:
        for name in FORECAST_FILES:
            candidate = self.path / name
            if candidate.exists():
                return candidate
        raise CrmForecastError(f"в {self.path} нет таблицы прогноза {FORECAST_FILES}")


@dataclass(frozen=True)
class DailyForecast:
    """Суточные объёмы прогноза: по агрегатам и суммой.

    Значения в выгрузке — объём за интервал опроса, поэтому сутки получаются
    суммой интервалов. Неполные сутки на краях горизонта исключаются: иначе
    первый и последний день выглядят провалом подачи.
    """

    run: ForecastRun
    interval_hours: float
    by_unit: dict[str, dict[date, float]] = field(default_factory=dict)
    total: dict[date, float] = field(default_factory=dict)
    partial_days: tuple[date, ...] = ()

    @property
    def period(self) -> tuple[date, date] | None:
        if not self.total:
            return None
        days = sorted(self.total)
        return days[0], days[-1]


def parse_timestamp(text: str) -> datetime:
    value = text.strip()
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise CrmForecastError(f"не разобрать время «{text}»")


def parse_value(text: str) -> float | None:
    """Число из выгрузки; пустое значение и NaN дают None."""
    value = (text or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return None if number != number else number  # NaN


def iter_rows(path: Path) -> Iterator[tuple[datetime, dict[str, float]]]:
    """(момент, {столбец: значение}) по строкам таблицы прогноза."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or TIMESTAMP_COLUMN not in reader.fieldnames:
            raise CrmForecastError(f"в {path.name} нет столбца «{TIMESTAMP_COLUMN}»")
        for row in reader:
            stamp = row.get(TIMESTAMP_COLUMN)
            if not stamp:
                continue
            values = {}
            for column, raw in row.items():
                if column == TIMESTAMP_COLUMN or column is None:
                    continue
                number = parse_value(raw)
                if number is not None:
                    values[column] = number
            yield parse_timestamp(stamp), values


def infer_interval_hours(timestamps: list[datetime]) -> float:
    """Шаг опроса — самый частый интервал между соседними моментами."""
    deltas = [
        (later - earlier).total_seconds() / 3600.0
        for earlier, later in zip(timestamps, timestamps[1:], strict=False)
        if later > earlier
    ]
    if not deltas:
        return DEFAULT_INTERVAL_HOURS
    return Counter(round(delta, 6) for delta in deltas).most_common(1)[0][0]


def read_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def discover_runs(object_dir: Path) -> list[ForecastRun]:
    """Прогоны внутри data/crm/<объект>, от старых имён к новым."""
    if not object_dir.is_dir():
        return []
    shared = read_metadata(object_dir / METADATA_FILE)
    runs = []
    for directory in sorted(p for p in object_dir.iterdir() if p.is_dir()):
        if not any((directory / name).exists() for name in FORECAST_FILES):
            continue
        meta = {**shared, **read_metadata(directory / METADATA_FILE)}
        run = read_metadata(directory / RUN_FILE)
        events = run.get("events")
        runs.append(
            ForecastRun(
                path=directory,
                code=directory.name,
                title=str(run.get("title") or directory.name),
                events=(
                    bool(events)
                    if events is not None
                    else (directory / EVENTS_FILE).exists()
                ),
                object_id=meta.get("object_id"),
                model=meta.get("recommended_model"),
            )
        )
    return runs


def aggregate_names(mapping_objects: Mapping[str, Any], object_id: str | None) -> dict[str, str]:
    """{PUMP_001: «НА-1»} по разделу objects из config/scada_tags.yaml."""
    if not object_id:
        return {}
    entry = mapping_objects.get(object_id) or {}
    return {str(unit): str(name) for unit, name in (entry.get("aggregates") or {}).items()}


def read_daily(run: ForecastRun, aggregates: Mapping[str, str] | None = None) -> DailyForecast:
    """Свести прогноз в суточные объёмы по агрегатам и станции.

    ``aggregates`` переводит код узла модели (``PUMP_001``) в код агрегата
    в БД (``НА-1``); без него ключами остаются коды узлов.
    """
    names = dict(aggregates or {})
    timestamps: list[datetime] = []
    by_unit: dict[str, dict[date, float]] = {}
    total: dict[date, float] = {}
    counts: Counter[date] = Counter()

    for stamp, values in iter_rows(run.table):
        timestamps.append(stamp)
        day = stamp.date()
        counts[day] += 1
        for column, value in values.items():
            match = PUMP_COLUMN.match(column)
            if match:
                unit = match.group("unit")
                key = names.get(unit, unit)
                by_unit.setdefault(key, {})
                by_unit[key][day] = by_unit[key].get(day, 0.0) + value
            elif column == TOTAL_COLUMN:
                total[day] = total.get(day, 0.0) + value

    if not timestamps:
        raise CrmForecastError(f"в {run.table.name} нет ни одной строки прогноза")

    interval_hours = infer_interval_hours(timestamps)
    expected = round(24.0 / interval_hours) if interval_hours else 0
    partial = tuple(sorted(day for day, count in counts.items() if count != expected))
    for day in partial:
        total.pop(day, None)
        for series in by_unit.values():
            series.pop(day, None)

    return DailyForecast(
        run=run,
        interval_hours=interval_hours,
        by_unit=by_unit,
        total=total,
        partial_days=partial,
    )
