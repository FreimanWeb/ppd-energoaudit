"""Нагнетательные скважины: индикаторная кривая приёмистости P–Q, ограничения.

ТЗ: оценка приёмистости и гидродинамических характеристик; выявление аномалий,
ограничения приёмистости.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class InjectivityCurve:
    """Линейная индикаторная кривая: Q = k·(p_заб − p₀) = k·p + b."""
    k: float                 # коэф. приёмистости, м³/сут/МПа (наклон)
    b: float                 # свободный член
    r2: float                # качество аппроксимации

    def flow_at(self, p: float) -> float:
        return self.k * p + self.b

    @property
    def injectivity_index(self) -> float:
        """Коэффициент приёмистости (наклон P–Q)."""
        return self.k


def fit_injectivity(points: list[tuple[float, float]]) -> InjectivityCurve:
    """МНК-аппроксимация P–Q линией (нужно ≥2 точки [(p, q), ...])."""
    pts = np.asarray(points, dtype=float)
    if pts.shape[0] < 2:
        raise ValueError("для кривой приёмистости нужно ≥2 точек")
    p, q = pts[:, 0], pts[:, 1]
    k, b = np.polyfit(p, q, 1)
    pred = k * p + b
    ss_res = float(np.sum((q - pred) ** 2))
    ss_tot = float(np.sum((q - q.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return InjectivityCurve(k=float(k), b=float(b), r2=r2)


@dataclass
class InjectivityCheck:
    q: float
    q_limit: float
    over_limit: bool
    margin: float            # запас до лимита, м³/сут


def check_injectivity_limit(q: float, q_limit: float) -> InjectivityCheck:
    """Проверка приёмистости против лимита (config/constraints.yaml: wells.injectivity_max)."""
    return InjectivityCheck(q=q, q_limit=q_limit, over_limit=q > q_limit,
                            margin=q_limit - q)


def detect_anomaly(curve: InjectivityCurve, r2_min: float = 0.9) -> bool:
    """Аномалия индикаторной линии: низкое R² (нелинейность/смена режима/трещина)."""
    return curve.r2 < r2_min
