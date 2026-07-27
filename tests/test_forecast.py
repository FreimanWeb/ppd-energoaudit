"""Тесты прогноза объёмов закачки (core/reservoir/forecast.py).

Это статистическая экстраполяция тренда — тесты проверяют её математику
(рост/спад/плоский тренд, доверительный интервал, агрегацию периодов),
а не какое-либо «правильное» инженерное предсказание.
"""

from __future__ import annotations

import pytest

from ppd_audit.core.reservoir.forecast import (aggregate_daily_to_periods,
                                                forecast_injection)


def test_rejects_too_few_points():
    with pytest.raises(ValueError):
        forecast_injection([100.0, 105.0])


def test_rejects_bad_horizon():
    with pytest.raises(ValueError):
        forecast_injection([100.0, 105.0, 110.0], horizon=0)


def test_flat_history_gives_flat_forecast():
    history = [500.0] * 12
    res = forecast_injection(history, horizon=6)
    assert res.trend_slope == pytest.approx(0.0, abs=1e-6)
    for p in res.points:
        assert p.value == pytest.approx(500.0, abs=1e-6)
    # без разброса в истории доверительный интервал вырождается в точку
    assert res.points[0].lower == pytest.approx(res.points[0].value)


def test_rising_trend_extrapolates_upward():
    history = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0]
    res = forecast_injection(history, horizon=3)
    assert res.trend_slope > 0
    assert res.points[0].value > history[-1]
    assert res.points[-1].value > res.points[0].value           # монотонно растёт дальше
    assert res.naive_baseline == pytest.approx(sum(history) / len(history))


def test_falling_trend_respects_floor():
    # резкое падение — экстраполяция на длинный горизонт должна упереться в 0,
    # а не уйти в физически невозможные отрицательные объёмы закачки
    history = [1000.0, 700.0, 400.0, 100.0]
    res = forecast_injection(history, horizon=24, min_value=0.0)
    assert all(p.value >= 0.0 for p in res.points)
    assert all(p.lower >= 0.0 for p in res.points)


def test_interval_widens_with_horizon():
    history = [90.0, 105.0, 95.0, 115.0, 100.0, 120.0, 108.0, 130.0]
    res = forecast_injection(history, horizon=12)
    width_first = res.points[0].upper - res.points[0].lower
    width_last = res.points[-1].upper - res.points[-1].lower
    assert width_last >= width_first        # неопределённость растёт дальше от факта


def test_total_sums_requested_periods():
    res = forecast_injection([500.0] * 6, horizon=12)
    assert res.total(3) == pytest.approx(1500.0, abs=1e-6)
    assert res.total() == pytest.approx(6000.0, abs=1e-6)


def test_aggregate_daily_to_periods_sums_correctly():
    daily = [10.0] * 90                      # 90 суток по 10 м³/сут
    monthly = aggregate_daily_to_periods(daily, days_per_period=30)
    assert monthly == [300.0, 300.0, 300.0]  # 3 полных месяца по 30 сут


def test_aggregate_daily_to_periods_drops_incomplete_tail():
    daily = [10.0] * 95                      # неполный последний период отбрасывается
    monthly = aggregate_daily_to_periods(daily, days_per_period=30)
    assert len(monthly) == 3


def test_aggregate_rejects_bad_period_length():
    with pytest.raises(ValueError):
        aggregate_daily_to_periods([1.0, 2.0], days_per_period=0)
