"""Источник исторической закачки и сценарного профиля для экономики."""

from __future__ import annotations

import math
from dataclasses import asdict
from datetime import date, timedelta

from ..core.reservoir.forecast import aggregate_daily_to_periods, forecast_injection
from ..db import AuditDatabase
from ..measures.economics import DEFAULT_HORIZON_YEARS, InjectionProfile, build_annual_profile
from .telemetry_view import daily_injection_series


def injection_profile(
    database: AuditDatabase,
    object_id: str,
    aggregate_id: str,
    base_annual_m3: float,
    *,
    horizon_years: int = DEFAULT_HORIZON_YEARS,
    period_days: int = 30,
) -> InjectionProfile | None:
    """Прогнозный профиль закачки по годам горизонта.

    Возвращает ``None``, если телеметрии не хватает на трендовую
    экстраполяцию (нужно ≥3 полных периода) — вызывающая сторона должна
    честно сказать об этом пользователю, а не подсовывать выдуманный профиль.
    """
    dates = database.telemetry_dates(object_id, aggregate_id)
    if len(dates) < 3:
        return None
    series = daily_injection_series(database, object_id, aggregate_id, dates[0], dates[-1])
    daily = [value for _, value in series]
    history = aggregate_daily_to_periods(daily, days_per_period=period_days)
    if len(history) < 3:
        return None

    horizon_periods = math.ceil(horizon_years * 365 / period_days)
    forecast = forecast_injection(history, horizon=horizon_periods)
    return build_annual_profile(
        [point.value for point in forecast.points],
        period_days=period_days,
        horizon_years=horizon_years,
        base_annual_m3=base_annual_m3,
        lower_values=[point.lower for point in forecast.points],
        upper_values=[point.upper for point in forecast.points],
        method=forecast.method,
        note=forecast.note,
    )


class InsufficientForecastData(ValueError):
    """Недостаточно суток или полных периодов для трендового прогноза."""

    def __init__(self, daily_count: int, period_count: int):
        super().__init__("нужно ≥3 исторических периода для прогноза тренда")
        self.daily_count = daily_count
        self.period_count = period_count


def forecast_series(
    database: AuditDatabase,
    object_id: str,
    aggregate_id: str,
    start_day: date,
    end_day: date,
    *,
    period_days: int = 30,
    horizon: int = 36,
) -> dict:
    """Единый ряд закачки и статистический прогноз из расчётного ядра."""
    series = daily_injection_series(database, object_id, aggregate_id, start_day, end_day)
    history = aggregate_daily_to_periods([value for _, value in series], period_days)
    if len(history) < 3:
        raise InsufficientForecastData(len(series), len(history))
    forecast = forecast_injection(history, horizon=horizon)
    used_count = len(history) * period_days
    last_day = date.fromisoformat(series[used_count - 1][0])
    return {
        "history": [
            {
                "period": i + 1 - len(history),
                "value": value,
                "period_start": series[i * period_days][0],
                "period_end": series[(i + 1) * period_days - 1][0],
            }
            for i, value in enumerate(history)
        ],
        "forecast": [
            {
                **asdict(point),
                "period_start": (
                    last_day + timedelta(days=(point.period - 1) * period_days + 1)
                ).isoformat(),
                "period_end": (last_day + timedelta(days=point.period * period_days)).isoformat(),
            }
            for point in forecast.points
        ],
        "unused_daily_count": len(series) - used_count,
        "missing_daily_count": (
            (date.fromisoformat(series[used_count - 1][0]) - date.fromisoformat(series[0][0])).days
            + 1
            - used_count
        ),
        "trend_slope": forecast.trend_slope,
        "naive_baseline": forecast.naive_baseline,
        "method": forecast.method,
        "estimate": forecast.estimate,
        "note": forecast.note,
        "period_days": period_days,
    }
