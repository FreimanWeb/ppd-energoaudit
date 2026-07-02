"""Характеристики насоса и пересчёт на вязкость — формулы (28)-(30) Методики.

- Число Рейнольдса (28) и коэффициенты пересчёта K_Q, K_H, K_η.
- Аппроксимация должных напора H_д (29) и КПД η_д (30) параболой по координатам
  паспортной кривой Q-H / Q-η (метод наименьших квадратов).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


def reynolds(q_nom: float, nu: float, d_outer_mm: float, wall_mm: float) -> float:
    """Число Рейнольдса по характеристике насоса (28).

    Re = Q_ном · 10⁷ / (9π · ν · d_вн),  Q_ном в м³/ч, ν в сСт, d_вн в мм.

    ВНИМАНИЕ: в PDF методики знаменатель напечатан как (D − d), где D — диаметр
    выкидной трубы, d — ТОЛЩИНА СТЕНКИ (табл. 8.2.1, п. 13–14). Внутренний диаметр
    физически равен D − 2d — реализовано это прочтение (вывод классического
    Re = 4Q/(πdν) в единицах методики требует именно внутренний диаметр).
    Отступление от буквы PDF зафиксировано: docs/audit_findings.md §В1.
    """
    inner = d_outer_mm - 2.0 * wall_mm
    return q_nom * 1.0e7 / (9.0 * math.pi * nu * inner)


@dataclass
class ViscosityFactors:
    """Коэффициенты пересчёта характеристик на вязкость (постоянны в 0,8..1,2·Q_ном)."""
    k_q: float = 1.0
    k_h: float = 1.0
    k_eta: float = 1.0


def viscosity_factors(re: float) -> ViscosityFactors:
    """Коэффициенты K_Q, K_H, K_η от Re.

    Для маловязких сред (вода, эмульсия с ν≈1 сСт) Re велик → пересчёт не нужен,
    K≈1. Для вязкой нефти коэффициенты < 1 (берутся по номограмме методики).
    Здесь реализован безопасный предел K=1 при большом Re; табличная номограмма
    подключается при необходимости (вход для пластовой/нефтесодержащей жидкости).
    """
    if re >= 1.0e5:
        return ViscosityFactors()
    # грубая монотонная аппроксимация снижения КПД с ростом вязкости (заглушка-оценка)
    k_eta = max(0.5, min(1.0, 0.5 + 0.5 * math.log10(max(re, 10.0)) / 5.0))
    return ViscosityFactors(k_q=1.0, k_h=min(1.0, k_eta + 0.05), k_eta=k_eta)


def fit_parabola(points: list[list[float]]) -> tuple[float, float, float]:
    """МНК-аппроксимация y = a·x² + b·x + c по точкам [[x, y], ...] (нужно ≥3)."""
    pts = np.asarray(points, dtype=float)
    if pts.shape[0] < 3:
        raise ValueError("для параболы нужно ≥3 точек паспортной кривой")
    a, b, c = np.polyfit(pts[:, 0], pts[:, 1], 2)
    return float(a), float(b), float(c)


def poly2(x: float, coeffs: tuple[float, float, float]) -> float:
    a, b, c = coeffs
    return a * x * x + b * x + c


def head_due(q: float, qh_points: list[list[float]]) -> float:
    """Должный напор H_д при подаче q (29) по координатам кривой Q-H."""
    return poly2(q, fit_parabola(qh_points))


def eta_due(q: float, qeta_points: list[list[float]]) -> float:
    """Должный КПД η_д при подаче q (30) по координатам кривой Q-η."""
    return poly2(q, fit_parabola(qeta_points))
