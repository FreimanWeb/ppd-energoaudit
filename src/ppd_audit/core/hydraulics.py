"""Гидравлический расчёт водоводов: Дарси–Вейсбах / Хазен–Вильямс.

ТЗ: стационарный гидрорасчёт; «неучтённые потери» = Δp_факт − Δp_расч по участкам,
флаг аномалий (порог 10 %). Эталон ДНС-7с: неучтённые 6,5 % (отчёт №31, разд. 2.3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .. import units


def velocity(q_m3h: float, d_inner_m: float) -> float:
    """Скорость потока, м/с: v = Q/A, A = πD²/4."""
    area = math.pi * d_inner_m ** 2 / 4.0
    return (q_m3h / 3600.0) / area


def reynolds_pipe(q_m3h: float, d_inner_m: float, nu_cst: float) -> float:
    """Число Рейнольдса потока в трубе: Re = v·D/ν (ν из сСт в м²/с)."""
    nu_m2s = nu_cst * 1.0e-6
    return velocity(q_m3h, d_inner_m) * d_inner_m / nu_m2s


def friction_factor_swamee_jain(re: float, rel_roughness: float) -> float:
    """Коэф. трения Дарси по Свами–Джейну (явная аппроксимация Колбрука).

    f = 0.25 / [log10(ε/D/3.7 + 5.74/Re^0.9)]²;  при Re<2300 — ламинар 64/Re.
    """
    if re < 2300:
        return 64.0 / max(re, 1.0)
    denom = math.log10(rel_roughness / 3.7 + 5.74 / re ** 0.9)
    return 0.25 / denom ** 2


def darcy_weisbach_dp(q_m3h: float, length_m: float, d_inner_m: float,
                      roughness_m: float, rho: float, nu_cst: float) -> float:
    """Потери давления на трение по Дарси–Вейсбаху, МПа.

    Δp = f·(L/D)·(ρ·v²/2).
    """
    v = velocity(q_m3h, d_inner_m)
    re = reynolds_pipe(q_m3h, d_inner_m, nu_cst)
    f = friction_factor_swamee_jain(re, roughness_m / d_inner_m)
    dp_pa = f * (length_m / d_inner_m) * (rho * v * v / 2.0)
    return dp_pa / 1.0e6


def hazen_williams_dp(q_m3h: float, length_m: float, d_inner_m: float,
                      c_factor: float, rho: float = 1000.0) -> float:
    """Потери давления по Хазену–Вильямсу, МПа (эмпирика для воды).

    h_f = 10.67·L·Q^1.852 / (C^1.852·D^4.87)   [Q в м³/с, D,L в м, h_f в м];
    Δp = ρ·g·h_f.
    """
    q_s = q_m3h / 3600.0
    h_f = 10.67 * length_m * q_s ** 1.852 / (c_factor ** 1.852 * d_inner_m ** 4.87)
    return rho * units.G * h_f / 1.0e6


def static_dp(rho: float, dz_m: float) -> float:
    """Статический перепад на геодезию, МПа: Δp = ρ·g·Δz."""
    return rho * units.G * dz_m / 1.0e6


@dataclass
class UnaccountedLosses:
    dp_fact: float          # фактический перепад (по манометрам), МПа
    dp_calc: float          # расчётный перепад, МПа
    residual: float         # Δp_факт − Δp_расч, МПа
    relative: float         # доля от расчётного
    anomaly: bool           # превышен порог


def unaccounted_losses(dp_fact: float, dp_calc: float, threshold: float = 0.10) -> UnaccountedLosses:
    """Неучтённые потери = Δp_факт − Δp_расч; флаг при |отн.| > порога.

    Эталон ДНС-7с: Δp_факт=2,45, Δp_расч=2,30 → 6,5 % (< 10 %).
    """
    residual = dp_fact - dp_calc
    rel = residual / dp_calc if dp_calc else float("nan")
    return UnaccountedLosses(dp_fact=dp_fact, dp_calc=dp_calc, residual=residual,
                             relative=rel, anomaly=abs(rel) > threshold)


def annual_hydraulic_loss_energy(dp_friction_mpa: float, q_m3h: float,
                                 t_year_h: float, eta: float = 1.0) -> float:
    """Годовые потери энергии на гидравлику трубопровода, кВт·ч/год.

    ΔW = (Δp_тр·Q/3.6)/η · T_год  — гидравлическая мощность на трение, отнесённая
    к КПД установки и годовой наработке.
    """
    return units.hydraulic_power_kw(dp_friction_mpa, q_m3h) / eta * t_year_h
