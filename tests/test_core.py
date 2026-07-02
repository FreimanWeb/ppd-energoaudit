"""Юнит-тесты расчётного ядра: КНС-декомпозиция, характеристика трубопровода,
ЭД, кривые, годовые потери. Проверка единиц и самосогласованности формул.
"""

import math

import pytest

from ppd_audit.core import curves, motor, specific_energy
from ppd_audit.core.pump import compute_regime, decompose_kns, nominal_efficiency


def test_nominal_efficiency_14():
    # η_ном = η_ЭД.ном · η_нас.ном (14) — пример ДНС-7с
    assert nominal_efficiency(0.94, 0.60) == pytest.approx(0.564, abs=1e-9)


def test_motor_efficiency_branches():
    # K_з ≥ 0,7 → η_эд ≈ η_ном
    assert motor.motor_efficiency(0.8, 0.94) == 0.94
    # K_з < 0,7 → снижение КПД
    eta = motor.motor_efficiency(0.6, 0.94, alpha=1.0)
    assert eta < 0.94 and eta == pytest.approx(0.933, abs=0.003)


def test_kns_decomposition_sums_to_electric():
    # 5-частная диаграмма КНС должна в сумме давать P_эл (контроль баланса 31-36)
    reg = compute_regime(q=100.0, rho=1000.0, p_in=0.2, p_out=10.0,
                         eta_nom=0.6, p_electric=600.0, p_bg=9.0)
    d = decompose_kns(reg)
    assert sum(d.components.values()) == pytest.approx(reg.p_electric, abs=1e-6)
    # ΔP_гидр + ΔP_НАдр = ΔP_др (32)
    assert d.dp_hydraulic + d.dp_na_throttle == pytest.approx(d.dp_throttle, abs=1e-9)


def test_pipe_characteristic_and_optimal_pressure():
    # H_т = H_с + K_т·Q² монотонно растёт; p_опт по (22)-(23)
    pipe = specific_energy.pipe_characteristic(
        h_fact=225.0, q=75.0, rho=1094.2, p_pp=0.5, p_in=0.398, h_pp=20.0, h_geo=5.0)
    assert pipe.head(60.0) < pipe.head(75.0)
    p_opt = specific_energy.optimal_pressure(q_day=1240.0, rho=1094.2, pipe=pipe)
    assert p_opt > 0


def test_annual_losses_44_47():
    # ΔW_кпд (44): Q_год·(УРЭ_ф − УРЭ_р)
    assert specific_energy.annual_loss_efficiency_by_sec(1000.0, 1.29, 1.19) == pytest.approx(100.0)
    # ΔW_ндт (47)
    assert specific_energy.annual_loss_ndt(1000.0, 1.29, 1.0) == pytest.approx(290.0)
    # ΔW_др (45): (p_вых−p_БГ)/(3.6·η_ном)·Q_год
    w = specific_energy.annual_loss_throttle(2.818, 2.0, 0.564, 446352.0)
    assert w == pytest.approx((2.818 - 2.0) / (3.6 * 0.564) * 446352.0, rel=1e-9)


def test_reynolds_and_viscosity_factors():
    re = curves.reynolds(q_nom=60.0, nu=1.05, d_outer_mm=150.0, wall_mm=8.0)
    assert re > 1.0e5                       # маловязкая среда
    vf = curves.viscosity_factors(re)
    assert vf.k_eta == 1.0 and vf.k_h == 1.0  # пересчёт не нужен


def test_parabola_fit():
    # y = 2x² + 3x + 1 точно восстанавливается
    a, b, c = curves.fit_parabola([[0, 1], [1, 6], [2, 15], [3, 28]])
    assert (a, b, c) == pytest.approx((2.0, 3.0, 1.0), abs=1e-6)
