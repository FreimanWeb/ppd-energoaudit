"""Прогноз объёмов закачки — статистическая экстраполяция тренда.

ЧТО ЭТО: линейная регрессия (МНК) по историческому ряду объёмов закачки
(например, м³/мес по скважине/объекту) с экстраполяцией на заданный горизонт
(по умолчанию 36 периодов = 3 года при месячных данных) и доверительным
интервалом по разбросу остатков регрессии. Для сравнения считается и «наивный»
ориентир — среднее за последние периоды (консервативная альтернатива тренду).

ЧЕМ ЭТО НЕ ЯВЛЯЕТСЯ: это НЕ гидродинамическая/геологическая модель пласта.
Метод не учитывает: план разработки месторождения и план ГТМ, ограничения
приёмистости и давления нагнетания, изменение фонда скважин (ввод/вывод),
взаимодействие с CRM-связностями из ``reservoir/crm.py``. Линейный тренд,
экстраполированный на годы вперёд, может дать физически неразумный результат
(уйти в отрицательные значения или расти без предела) — поэтому результат
всегда сопровождается наивным ориентиром и явной пометкой ``estimate=True``,
и его стоит использовать только как индикативную, а не проектную оценку.

Если в проекте появится нормальная гидродинамическая модель или план закачки —
подставлять его результат вместо этого модуля, интерфейс тот же (список
периодов вперёд → значения), см. ``ForecastResult``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class ForecastPoint:
    period: int      # индекс периода вперёд, считая от конца истории (1..horizon)
    value: float      # прогнозное значение (по тренду)
    lower: float      # нижняя граница ориентировочного 95%-интервала
    upper: float      # верхняя граница


@dataclass
class ForecastResult:
    method: str
    historical_periods: int
    horizon: int
    points: list[ForecastPoint] = field(default_factory=list)
    trend_slope: float | None = None       # прирост/спад за период (та же ед. изм., что и history)
    naive_baseline: float | None = None    # среднее последних периодов (для сравнения)
    estimate: bool = True
    note: str = ""

    def total(self, periods: int | None = None) -> float:
        """Суммарный прогнозный объём за первые `periods` периодов (по умолчанию — весь горизонт)."""
        n = self.horizon if periods is None else min(periods, self.horizon)
        return round(sum(p.value for p in self.points[:n]), 2)


def _linreg(y: np.ndarray) -> tuple[float, float, float]:
    x = np.arange(len(y), dtype=float)
    a, b = np.polyfit(x, y, 1)
    resid = y - (a * x + b)
    sigma = float(np.std(resid, ddof=2)) if len(y) > 2 else 0.0
    return a, b, sigma


def forecast_injection(history: list[float], *, horizon: int = 36,
                        min_value: float = 0.0,
                        confidence_z: float = 1.96,
                        naive_window: int = 6) -> ForecastResult:
    """Прогноз объёма закачки трендовой экстраполяцией.

    Параметры
    ---------
    history : список исторических объёмов закачки одной периодичности
        (например, м³/мес), от старых к новым. Нужно ≥3 точек.
    horizon : на сколько периодов вперёд считать прогноз
        (36 при месячных периодах = 3 года; 3 — если сами периоды уже годовые).
    min_value : физический пол значения (закачка не может быть отрицательной).
    confidence_z : множитель для доверительного интервала (1.96 ≈ 95%).
    naive_window : сколько последних периодов усреднять для наивного ориентира.
    """
    y = np.asarray(history, dtype=float)
    if y.size < 3:
        raise ValueError("нужно ≥3 исторических периода для прогноза тренда")
    if horizon < 1:
        raise ValueError("horizon должен быть ≥1")

    a, b, sigma = _linreg(y)
    naive = float(np.mean(y[-min(naive_window, y.size):]))

    n0 = y.size
    points = []
    for k in range(1, horizon + 1):
        x = n0 - 1 + k
        val = max(min_value, a * x + b)
        # приближённый доверительный интервал: растёт с горизонтом (экстраполяция
        # тем менее надёжна, чем дальше от конца истории) — sqrt(1 + k/n0) как
        # огрубление стандартной формулы дисперсии прогноза линейной регрессии.
        margin = confidence_z * sigma * math.sqrt(1.0 + k / n0) if sigma > 0 else 0.0
        points.append(ForecastPoint(period=k, value=round(val, 2),
                                     lower=round(max(min_value, val - margin), 2),
                                     upper=round(val + margin, 2)))

    return ForecastResult(
        method="linear-trend",
        historical_periods=n0,
        horizon=horizon,
        points=points,
        trend_slope=round(float(a), 4),
        naive_baseline=round(naive, 2),
        estimate=True,
        note="Статистическая экстраполяция тренда (МНК) по факту, не гидродинамическая "
             "модель пласта; не учитывает план ГТМ/фонда скважин и ограничения приёмистости. "
             "См. docstring модуля.",
    )


def aggregate_daily_to_periods(daily: list[float], days_per_period: int = 30) -> list[float]:
    """Свернуть суточный ряд закачки (м³/сут) в объёмы по периодам (сумма за period).

    Удобно, если исходные данные — суточная телеметрия (как ряды из
    ``ingest``), а прогноз нужен по месяцам/кварталам.
    """
    if days_per_period < 1:
        raise ValueError("days_per_period должен быть ≥1")
    n_periods = len(daily) // days_per_period
    return [float(np.sum(daily[i * days_per_period:(i + 1) * days_per_period]))
            for i in range(n_periods)]
