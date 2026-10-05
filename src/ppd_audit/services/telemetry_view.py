"""Окна телеметрии и суточная закачка без зависимости от UI."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from ..db import AuditDatabase
from .telemetry_audit import telemetry_day_status


USABLE_DAY_STATUSES = ("ready", "snapshot", "unfit")


def last_usable_day(
    database: AuditDatabase, object_id: str, aggregate_id: str, scan_limit: int = 60
):
    """Последние сутки, за которые вообще строится режим.

    Дашборд открывается на них. Просто «последняя дата с суточными итогами»
    не годится: на КНС-ОПУ подача агрегата получается распределением
    станционного расхода, и почти простоявшие сутки дают крохотный, но
    ненулевой объём — открывать дашборд на них бессмысленно. Идём от конца
    назад по датам, пока не найдём сутки со статусом не «insufficient».

    Просмотр ограничен ``scan_limit`` сутками: у агрегата, который не считается
    в принципе (нет паспортных КПД, стоит месяцами), полный перебор 400 дней
    занял бы секунды на каждом открытии. Не нашли — возвращаем None, и вызов
    откатывается на прежнее умолчание.
    """
    dates = database.telemetry_dates(object_id, aggregate_id)
    if not dates:
        return None
    for day in reversed(dates[-scan_limit:]):
        if telemetry_day_status(database, object_id, aggregate_id, day) in USABLE_DAY_STATUSES:
            return day
    return None


def telemetry_for_window(
    database: AuditDatabase, object_id: str, aggregate_id: str, start: datetime, end: datetime
) -> list[dict]:
    database_ = database
    rows = database_.measurements_in_window(
        object_id, aggregate_id, start, end, include_station=True
    )
    state_rows = database_.state_measurements_in_window(
        object_id, aggregate_id, start, end, include_end=True
    )
    return [
        row for row in rows if row["metric"] not in {"p_in", "p_out", "p_bg", "power"}
    ] + state_rows


def telemetry_for_day(
    database: AuditDatabase, object_id: str, aggregate_id: str, day: date
) -> list[dict]:
    """События агрегата за сутки и актуальное на начало суток давление."""
    start = datetime.combine(day, datetime.min.time())
    return telemetry_for_window(database, object_id, aggregate_id, start, start + timedelta(days=1))


def telemetry_for_period(
    database: AuditDatabase, object_id: str, aggregate_id: str, start_day: date, end_day: date
) -> list[dict]:
    """Сырые точки агрегата и станции за выбранные дни включительно."""
    start = datetime.combine(start_day, datetime.min.time())
    end = datetime.combine(end_day + timedelta(days=1), datetime.min.time())
    return telemetry_for_window(database, object_id, aggregate_id, start, end)


def daily_injection_series(
    database: AuditDatabase, object_id: str, aggregate_id: str, start_day: date, end_day: date
) -> list[tuple[str, float]]:
    """Суточные объёмы закачки (метрика q_day) по датам, от старых к новым.

    Приоритет — значение самого агрегата; станционное берётся только там, где
    своего нет. Общая точка входа для вкладки прогноза и для экономики
    мероприятий, чтобы обе считали ряд одинаково.
    """
    rows = telemetry_for_period(database, object_id, aggregate_id, start_day, end_day)
    by_date: dict[str, float] = {}
    for row in rows:
        if row["metric"] != "q_day":
            continue
        day_key = row["timestamp"][:10]
        if row["is_station"] and day_key in by_date:
            continue
        if (not row["is_station"]) or day_key not in by_date:
            by_date[day_key] = row["value"]
    return sorted(by_date.items())
