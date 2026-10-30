"""Проверка единиц и базовых соотношений (Методика, разд. 8)."""

import math

from ppd_audit import units


def test_kgfcm2_to_mpa():
    # Методика: множитель 0,098
    assert math.isclose(units.kgfcm2_to_mpa(10.0), 0.98, rel_tol=1e-9)


def test_head_from_pressure_dns7s():
    # H_ф = (p_вых-p_вх)·1e6/(ρ·g); эталон аудита №31: ≈225,4 м
    h = units.head_from_pressure(2.818 - 0.398, rho=1094.2)
    assert math.isclose(h, 225.4, abs_tol=0.5)


def test_hydraulic_power_dns7s():
    # P_гидр = Δp·Q/3.6; эталон ≈50,5 кВт
    p = units.hydraulic_power_kw(2.818 - 0.398, q_m3h=75.17)
    assert math.isclose(p, 50.5, abs_tol=0.2)
