"""Характеристики насоса и пересчёт на вязкость — формулы (28)-(30) Методики.

- Число Рейнольдса (28) и коэффициенты пересчёта K_Q, K_H, K_η.
- Аппроксимация должных напора H_д (29) и КПД η_д (30) параболой по координатам
  паспортной кривой Q-H / Q-η (метод наименьших квадратов).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..spec import PumpKind, PumpSpec


def reynolds(q_nom: float, nu: float, d_outer_mm: float, wall_mm: float) -> float:
    """Число Рейнольдса по характеристике насоса (28).

    Re = Q_ном · 10⁷ / (9π · ν · d_вн),  Q_ном в м³/ч, ν в сСт, d_вн в мм.

    D — наружный диаметр выкидной трубы, d — толщина стенки; знаменатель
    использует внутренний диаметр D − 2d, как в формуле (28) методики.
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
    """МНК y = a·x² + b·x + c; не менее трёх различных конечных точек."""
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2 or pts.shape[0] < 3:
        raise ValueError("для параболы нужно ≥3 точек характеристики")
    if not np.isfinite(pts).all() or len(np.unique(pts[:, 0])) != len(pts):
        raise ValueError("точки должны быть конечными с различными подачами")
    a, b, c = np.polyfit(pts[:, 0], pts[:, 1], 2)
    return float(a), float(b), float(c)


def poly2(x: float, coeffs: tuple[float, float, float]) -> float:
    a, b, c = coeffs
    return a * x * x + b * x + c


def _bounded_value(q: float, points: list[list[float]], maximum: float) -> float | None:
    if len(points) < 3 or not math.isfinite(q):
        return None
    if not min(point[0] for point in points) <= q <= max(point[0] for point in points):
        return None
    value = poly2(q, fit_parabola(points))
    return value if math.isfinite(value) and 0 <= value <= maximum else None


def head_due(q: float, qh_points: list[list[float]]) -> float | None:
    """Опорный H (29) только внутри диапазона исходных точек Q-H."""
    return _bounded_value(q, qh_points, math.inf)


def eta_due(q: float, qeta_points: list[list[float]]) -> float | None:
    """Опорный η (30), в долях, без экстраполяции и обрезки невалидного МНК."""
    return _bounded_value(q, qeta_points, 1.0)


@dataclass(frozen=True)
class PumpCharacteristic:
    h_due_m: float | None
    eta_due: float | None
    qh_status: str
    qeta_status: str
    origin: str
    verified: bool
    notes: tuple[str, ...]


def evaluate_pump_characteristic(pump: PumpSpec, q: float) -> PumpCharacteristic:
    """Оценить обе кривые, отдельно от подтверждения применимости к оборудованию."""
    source = pump.curve_source
    origin = source.kind if source is not None else "unverified"
    notes = []
    blocked = None
    if pump.kind == PumpKind.positive_displacement:
        blocked = "not_applicable"
        notes.append("Q-H/Q-η центробежного насоса неприменимы к объёмному насосу.")
    elif source is not None:
        if source.model and source.model.replace(" ", "").casefold() != (
            pump.model.replace(" ", "").casefold()
        ):
            blocked = "model_mismatch"
            notes.append("Обозначение насоса не совпадает с привязкой характеристики.")
        elif (
            source.speed_rpm is not None
            and pump.n_rpm is not None
            and not math.isclose(source.speed_rpm, pump.n_rpm, rel_tol=1e-6)
        ):
            blocked = "speed_mismatch"
            notes.append("Частота вращения не совпадает с условиями характеристики.")

    def evaluate(points, evaluator, label):
        if blocked:
            return None, blocked
        if not points:
            notes.append(f"{label}: исходные точки отсутствуют.")
            return None, "missing"
        if len(points) < 3:
            notes.append(f"{label}: для квадратичной аппроксимации нужны ≥3 точки.")
            return None, "insufficient_points"
        lower, upper = min(p[0] for p in points), max(p[0] for p in points)
        if not lower <= q <= upper:
            notes.append(f"{label}: Q={q:g} вне диапазона {lower:g}–{upper:g} м³/ч.")
            return None, "out_of_range"
        value = evaluator(q, points)
        if value is None:
            notes.append(f"{label}: аппроксимация даёт физически недопустимое значение.")
            return None, "invalid_fit"
        return value, "within_range"

    head, h_status = evaluate(pump.curve_qh, head_due, "Q-H")
    eta, eta_status = evaluate(pump.curve_qeta, eta_due, "Q-η")
    binding_verified = bool(
        source is not None
        and source.verified
        and source.model
        and source.speed_rpm is not None
        and pump.n_rpm is not None
        and blocked is None
    )
    if not binding_verified:
        notes.append("Применимость характеристики к установленному насосу не подтверждена.")
    if source is not None and source.note:
        notes.append(source.note)
    return PumpCharacteristic(
        head,
        eta,
        h_status,
        eta_status,
        origin,
        binding_verified and head is not None and head > 0 and eta is not None and eta > 0,
        tuple(notes),
    )
