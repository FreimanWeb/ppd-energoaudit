"""Юнит-тесты расчётного ядра: КНС-декомпозиция, характеристика трубопровода,
ЭД, кривые, годовые потери. Проверка единиц и самосогласованности формул +
негативные тесты самопроверок (аудит ядра 02.07.2026).
"""

import math

import pytest

from ppd_audit.core import curves, motor, specific_energy
from ppd_audit.core.audit import audit_aggregate
from ppd_audit.core.pump import (RegimeResult, compute_regime, decompose_kns,
                                 decompose_pumping, nominal_efficiency)
from ppd_audit.spec import (AggregateSpec, Branch, MotorSpec, PumpSpec,
                            RegimeMeasurement)


def test_nominal_efficiency_14():
    # η_ном = η_ЭД.ном · η_нас.ном (14) — пример ДНС-7с
    assert nominal_efficiency(0.94, 0.60) == pytest.approx(0.564, abs=1e-9)


def test_formula_15_with_vfd_and_gear():
    # η_ном = η_пч·η_ЭД.ном·η_тр·η_нас.ном (15)
    assert nominal_efficiency(0.94, 0.60, eta_vfd=0.97, eta_gear=0.98) == \
        pytest.approx(0.97 * 0.94 * 0.98 * 0.60, abs=1e-12)
    # и через спец агрегата (vfd → η_пч=0,97)
    agg = AggregateSpec(id="т", pump=PumpSpec(eta_nom=0.60),
                        motor=MotorSpec(eta_nom=0.94), vfd=True, transmission_eff=0.98)
    assert agg.nominal_efficiency() == pytest.approx(0.97 * 0.94 * 0.98 * 0.60, abs=1e-12)


def test_motor_efficiency_branches():
    # K_з ≥ 0,7 → η_эд ≈ η_ном
    assert motor.motor_efficiency(0.8, 0.94) == 0.94
    # K_з < 0,7 → снижение КПД
    eta = motor.motor_efficiency(0.6, 0.94, alpha=1.0)
    assert eta < 0.94 and eta == pytest.approx(0.933, abs=0.003)


def test_synchronous_motor_alpha():
    """(26): синхронный ЭД (СТД/СДН) → α=2; определяется по серии двигателя."""
    from ppd_audit.spec import infer_motor_synchronous
    assert infer_motor_synchronous("СТД -800-2РУХЛ4")
    assert infer_motor_synchronous("СДН-14-59-10")
    assert not infer_motor_synchronous("5АИ 355 S4Y2")
    assert not infer_motor_synchronous("ВАО3-280М-2У2,5")
    assert MotorSpec(model="СТД-800", synchronous=True).alpha == 2.0
    # при K_з<0,7 α меняет η_эд.р: β(α=2)=1,5 > β(α=1)=1,25 при K_з=0,5 →
    # у синхронного больше доля постоянных потерь → расчётный КПД ниже
    eta_sync = motor.motor_efficiency(0.5, 0.96, alpha=2.0)
    eta_async = motor.motor_efficiency(0.5, 0.96, alpha=1.0)
    assert eta_sync < eta_async


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


# ---------- (18): УРЭ оптимальный ----------

def test_sec_optimal_uses_ndt():
    # УРЭ_опт = (p_опт − p_вх)/(3.6·η_ндт) (18); для КНС p_опт = p_БГ
    sec = specific_energy.sec_optimal(9.0, 0.2, 0.7)
    assert sec == pytest.approx((9.0 - 0.2) / (3.6 * 0.7), rel=1e-12)


# ---------- (46): годовые потери на циклический режим ----------

def test_annual_loss_cyclic():
    # ΔW_ц = (p_вых − p_опт)/(3.6·η_ном)·Q_год (46)
    w = specific_energy.annual_loss_cyclic(2.818, 2.5, 0.564, 446352.0)
    assert w == pytest.approx((2.818 - 2.5) / (3.6 * 0.564) * 446352.0, rel=1e-12)
    # непрерывный режим (p_вых = p_опт) → потерь нет
    assert specific_energy.annual_loss_cyclic(2.5, 2.5, 0.564, 446352.0) == 0.0


# ---------- Синтетический агрегат для сквозных проверок оркестратора ----------

def _make_transfer_agg(**kw) -> AggregateSpec:
    """Центробежный агрегат перекачки с измеренным режимом (синтетика)."""
    d = dict(
        id="Т-1",
        pump=PumpSpec(model="ЦНС 60-250", eta_nom=0.60,
                      q_nom=60.0, h_nom=250.0),
        motor=MotorSpec(model="ВАО", p_nom=160.0, eta_nom=0.94),
        regime=RegimeMeasurement(rho=1000.0, p_in=0.4, p_out=2.8,
                                 q_fact=75.0, p_electric=97.0, t_year=7000.0),
    )
    d.update(kw)
    return AggregateSpec(**d)


def test_formula_27_with_vfd_gear():
    """(27): η_нас = η_НА/(η_эд.р·η_пч·η_ред) — η_пч и η_ред учитываются;
    баланс (43) остаётся сведённым при ПЧ/редукторе."""
    agg = _make_transfer_agg(vfd=True, transmission_eff=0.98)
    res = audit_aggregate(agg, Branch.transfer)
    eta_na = res.regime.eta_unit
    expected = eta_na / (res.eta_motor_real * 0.97 * 0.98)
    assert res.eta_pump == pytest.approx(expected, rel=1e-9)
    assert res.decomposition.balance_ok
    # η_ном включает η_пч·η_тр (15)
    assert res.regime.eta_nom == pytest.approx(0.97 * 0.94 * 0.98 * 0.60, rel=1e-9)


def test_head_due_from_curve():
    """(29): H_д по паспортной кривой Q-H подключён к оркестратору."""
    curve = [[40.0, 280.0], [60.0, 250.0], [80.0, 200.0]]  # парабола через 3 точки
    agg = _make_transfer_agg(pump=PumpSpec(model="ЦНС 60-250", eta_nom=0.60,
                                           curve_qh=curve))
    res = audit_aggregate(agg, Branch.transfer)
    assert res.h_due == pytest.approx(curves.head_due(75.0, curve), rel=1e-9)
    assert "29" in res.trace


def test_eta_due_from_curve():
    """(30): η_д по паспортной кривой Q-η приоритетнее η_ном; фикс. η из отчёта — вторая."""
    curve = [[40.0, 0.50], [60.0, 0.60], [80.0, 0.55]]
    agg = _make_transfer_agg(pump=PumpSpec(model="ЦНС 60-250", eta_nom=0.60,
                                           curve_qeta=curve))
    res = audit_aggregate(agg, Branch.transfer)
    assert res.trace["30"]["value"] == pytest.approx(curves.eta_due(75.0, curve), abs=5e-5)
    # без кривой, но с eta_pump_due — берётся он
    agg2 = _make_transfer_agg(eta_pump_due=0.576)
    res2 = audit_aggregate(agg2, Branch.transfer)
    assert res2.trace["30"]["value"] == pytest.approx(0.576, abs=1e-9)


# ---------- Негативные тесты самопроверок ----------

def test_balance_43_detects_inconsistency():
    """Баланс (43) ловит рассогласованные входы: η_НА, не равный P_гидр/P_эл,
    даёт ненулевую невязку и balance_ok=False."""
    reg = RegimeResult(q=75.0, rho=1000.0, p_in=0.4, p_out=2.8, eta_nom=0.564,
                       h_fact=244.6, p_hydraulic=50.0, p_electric=97.0,
                       eta_unit=0.62)   # согласованное значение было бы 50/97=0.515
    d = decompose_pumping(reg, eta_motor_nom=0.94, eta_motor_real=0.93, eta_due=0.576)
    assert not d.balance_ok
    assert abs(d.balance_residual) > 1.0   # кВт — невязка заметная


def test_kns_decomposition_negative_no_pbg():
    """Декомпозиция КНС без p_БГ невозможна — понятная ошибка, а не мусор."""
    reg = compute_regime(q=100.0, rho=1000.0, p_in=0.2, p_out=10.0,
                         eta_nom=0.6, p_electric=600.0)   # p_bg не задан
    with pytest.raises(ValueError, match="БГ|bg"):
        decompose_kns(reg)


def test_compute_regime_requires_power_inputs():
    """(12): без P_эл и без пары (W, T) режим не считается — понятная ошибка."""
    with pytest.raises(ValueError, match="P_эл|W"):
        compute_regime(q=100.0, rho=1000.0, p_in=0.2, p_out=10.0, eta_nom=0.6)
