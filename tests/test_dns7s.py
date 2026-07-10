"""Верификационный кейс ДНС-7с: воспроизведение энергоаудита №31 (18.12.2025).

Расчётное ядро по эталонному режиму (Табл. 3.1 отчёта, агрегат Н-4, 10.10.2025)
должно воспроизводить показатели аудита в допусках. Эталонные значения — в
config/plants/dns7s.yaml → reference_regime.expected.
"""

import pytest

from ppd_audit.config import load_plant
from ppd_audit.core.audit import run_pump_audit


@pytest.fixture(scope="module")
def result():
    return run_pump_audit("dns7s")


@pytest.fixture(scope="module")
def expected():
    return load_plant("dns7s").reference_regime["expected"]


def test_head_and_powers(result, expected):
    g = result.regime
    assert g.h_fact == pytest.approx(expected["h_fact"], abs=0.5)        # (8)
    assert g.p_hydraulic == pytest.approx(expected["p_hydraulic"], abs=0.1)  # (11)
    assert g.p_electric == pytest.approx(expected["p_electric"], abs=0.1)


def test_efficiencies(result, expected):
    g = result.regime
    assert g.eta_unit == pytest.approx(expected["eta_fact"], abs=0.005)      # (13) η_НА
    assert g.eta_nom == pytest.approx(expected["eta_nom"], abs=0.001)        # (14) η_ном
    assert result.eta_motor_real == pytest.approx(expected["eta_motor_calc"], abs=0.002)  # (25-26)
    assert result.eta_pump == pytest.approx(expected["eta_pump"], abs=0.002)  # (27)


def test_specific_energy(result, expected):
    assert result.sec_fact == pytest.approx(expected["sec_fact"], abs=0.005)  # (16)
    assert result.sec_calc == pytest.approx(expected["sec_calc"], abs=0.002)  # (17)
    # факт превышает расчёт на ~0,101 кВт·ч/м³ (по отчёту)
    assert (result.sec_fact - result.sec_calc) == pytest.approx(0.101, abs=0.005)


def test_load_factor(result, expected):
    # Строгая формула (24) даёт 0,571; отчёт отображает 0,6 (= P_эл/P_ном).
    # Допускаем оба прочтения — критичен не K_з, а η_эд.р (проверен выше).
    assert 0.55 <= result.load_factor <= 0.62


def test_annual_efficiency_loss(result, expected):
    # ΔW_НА = ΔP_КПД(38)·T_год — ключевой эталон аудита: 53 242,9 кВт·ч/год
    assert result.dw_efficiency == pytest.approx(expected["dw_efficiency"], rel=0.005)


def test_power_balance_43(result):
    # Контроль баланса мощностей (43): ΔP_КПД = ΔP_вязк+ΔP_неопт+ΔP_ЭД+ΔP_изн
    d = result.decomposition
    assert d.balance_ok
    assert abs(d.balance_residual) < 1e-6


def test_unaccounted_hydraulic_losses():
    """Неучтённые потери напорного трубопровода ДНС-7с (отчёт №31, разд. 2.3): 6,5 %.

    Δp_факт = p_вых − p_ДНС3с(замер) = 2,8 − 0,35 = 2,45 МПа;
    Δp_расч = p_вых − p_ДНС3с(расчёт) = 2,8 − 0,50 = 2,30 МПа; |откл.| = 6,5 % (< 10 %).
    """
    from ppd_audit.core.hydraulics import unaccounted_losses
    u = unaccounted_losses(dp_fact=2.8 - 0.35, dp_calc=2.8 - 0.5)
    assert u.relative == pytest.approx(0.065, abs=0.002)
    assert not u.anomaly
