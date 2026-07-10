"""Тесты остальной цепочки ППД: водоводы, узлы, скважины, пласт, мероприятия,
декомпозиция, оптимизация."""

import math

import pytest

from ppd_audit.config import load_constraints
from ppd_audit.core import hydraulics, nodes, wells, zra
from ppd_audit.core.audit import run_pump_audit
from ppd_audit.core.reservoir import CRMLite, DemoReservoir, ReservoirInput, get_model
from ppd_audit.decomposition import build_loss_map
from ppd_audit.measures import suggest_measures
from ppd_audit.optimize import optimize_setpoint


# ---------- Водоводы ----------

def test_unaccounted_losses_dns7s():
    # эталон отчёта №31: Δp_факт=2,45, Δp_расч=2,30 → 6,5 % (< 10 %)
    u = hydraulics.unaccounted_losses(2.45, 2.30)
    assert u.relative == pytest.approx(0.065, abs=0.002)
    assert not u.anomaly


def test_unaccounted_losses_anomaly_flag():
    u = hydraulics.unaccounted_losses(3.0, 2.0)  # +50 %
    assert u.anomaly


def test_darcy_weisbach_positive_and_monotone():
    dp1 = hydraulics.darcy_weisbach_dp(50, 1000, 0.15, 5e-5, 1000, 1.0)
    dp2 = hydraulics.darcy_weisbach_dp(100, 1000, 0.15, 5e-5, 1000, 1.0)
    assert 0 < dp1 < dp2          # больше расход → больше потери


def test_hazen_williams_sane():
    dp = hydraulics.hazen_williams_dp(50, 1000, 0.15, c_factor=120)
    assert dp > 0


def test_annual_hydraulic_energy():
    w = hydraulics.annual_hydraulic_loss_energy(0.18, 75.17, 7000, eta=0.564)
    assert w > 0


# ---------- ЗРА / штуцеры ----------

def test_throttle_loss():
    # Δp_задв = 0,77 МПа на штуцере; проверяем (31)-(32)-(45)
    t = zra.throttle_loss(p_before=14.1, p_after=13.33, q=47.4, eta_nom=0.815,
                          t_year=5411, tariff=4.68)
    assert t.dp_throttle == pytest.approx(0.77, abs=1e-9)
    assert t.power_hydraulic == pytest.approx(0.77 * 47.4 / 3.6, rel=1e-6)
    assert t.power_electric > t.power_hydraulic        # /η_ном > гидравлической
    assert t.annual_kwh > 0 and t.annual_rub == pytest.approx(t.annual_kwh * 4.68)


# ---------- Распредузлы ----------

def test_material_balance():
    b = nodes.material_balance("узел-1", {"вход": 1000.0}, {"в1": 600.0, "в2": 380.0})
    assert b.residual == pytest.approx(20.0)
    assert b.relative == pytest.approx(0.02)
    assert not b.anomaly


def test_material_balance_anomaly():
    b = nodes.material_balance("узел-2", {"вход": 1000.0}, {"в1": 800.0})
    assert b.anomaly


# ---------- Скважины ----------

def test_injectivity_fit_linear():
    pts = [(5.0, 100.0), (10.0, 200.0), (15.0, 300.0)]  # Q = 20·p
    c = wells.fit_injectivity(pts)
    assert c.injectivity_index == pytest.approx(20.0, abs=1e-6)
    assert c.r2 == pytest.approx(1.0, abs=1e-9)


def test_injectivity_limit():
    chk = wells.check_injectivity_limit(1100.0, 1000.0)
    assert chk.over_limit and chk.margin == pytest.approx(-100.0)


# ---------- Отклик пласта ----------

def test_reservoir_demo():
    data = ReservoirInput(injectors=["i1", "i2"], producers=["p1"],
                          injection={"i1": [10, 10], "i2": [20, 20]},
                          production={"p1": [15, 15]})
    res = DemoReservoir().fit(data)
    assert res.connectivity["p1"] == {"i1": 0.5, "i2": 0.5}
    assert res.estimate


def test_reservoir_crm_recovers_connectivity():
    # p1 = 0.6·i1 + 0.4·i2
    i1 = [10, 20, 30, 40, 50]
    i2 = [50, 40, 30, 20, 10]
    p1 = [0.6 * a + 0.4 * b for a, b in zip(i1, i2)]
    data = ReservoirInput(injectors=["i1", "i2"], producers=["p1"],
                          injection={"i1": i1, "i2": i2}, production={"p1": p1})
    res = CRMLite().fit(data)
    assert res.connectivity["p1"]["i1"] == pytest.approx(0.6, abs=0.05)
    assert res.connectivity["p1"]["i2"] == pytest.approx(0.4, abs=0.05)


def test_reservoir_factory():
    assert isinstance(get_model("demo"), DemoReservoir)
    assert isinstance(get_model("crm-lite"), CRMLite)
    with pytest.raises(ValueError):
        get_model("несуществующая")


# ---------- Декомпозиция / мероприятия / оптимизация (на реальном объекте) ----------

@pytest.fixture(scope="module")
def audit_kns25():
    return run_pump_audit("kns25", "НА-2")


def test_loss_map_sums_to_electric(audit_kns25):
    lm = build_loss_map(audit_kns25)
    total = sum(i.power_kw for i in lm.items)
    assert total == pytest.approx(lm.p_electric, rel=1e-6)


def test_measures_suggested(audit_kns25):
    evals = suggest_measures(audit_kns25)
    assert evals, "ожидаются применимые мероприятия"
    for e in evals:
        assert e.energy_saving_kwh > 0
        if e.capex_krub > 0:
            assert e.payback_years is not None and e.payback_years > 0


def test_setpoint_optimization(audit_kns25):
    opt = optimize_setpoint(audit_kns25, load_constraints())
    assert opt.optimal_p_out <= opt.current_p_out
    assert opt.saving_kwh_year >= 0
    assert isinstance(opt.within_constraints, bool)
