"""Тесты экономики мероприятий на горизонте (measures/economics.py).

Проверяется математика: свёртка прогноза в годовые объёмы, масштабирование
эффекта объёмом закачки, NPV/IRR и обе окупаемости. Это не проверка того, что
прогноз «правильный» — прогноз здесь входные данные.
"""

from __future__ import annotations

import pytest

from ppd_audit.measures import Measure, MeasureClass
from ppd_audit.measures.economics import (
    InjectionProfile,
    build_annual_profile,
    evaluate_horizon,
    internal_rate_of_return,
    net_present_value,
    payback_from_cumulative,
    suggest_measures_over_horizon,
)


TARIFF = 4.0  # руб/кВт·ч — круглый, чтобы деньги считались в уме


class _FakeAudit:
    """`evaluate` из registry передаёт audit только в saving_fn/applicable_fn."""


def _measure(
    saving_kwh: float,
    *,
    capex: float = 0.0,
    exponent: float = 1.0,
    cls: MeasureClass = MeasureClass.conditional,
    measure_id: str = "test",
) -> Measure:
    return Measure(
        measure_id,
        "Тестовое мероприятие",
        cls,
        "тест",
        capex,
        saving_fn=lambda _a: saving_kwh,
        applicable_fn=lambda _a: saving_kwh > 0,
        volume_exponent=exponent,
    )


# ───────────────────────── профиль закачки ─────────────────────────


def test_flat_profile_has_unit_ratios():
    profile = InjectionProfile.flat(1000.0, 3)
    assert profile.horizon_years == 3
    assert profile.ratios() == [1.0, 1.0, 1.0]
    assert profile.total_m3 == pytest.approx(3000.0)


def test_flat_profile_rejects_bad_horizon():
    with pytest.raises(ValueError):
        InjectionProfile.flat(1000.0, 0)


def test_build_annual_profile_rolls_periods_into_years():
    # 100 м³ за каждый 30-суточный период = 10/3 м³/сут → 365·10/3 ≈ 1216,67 м³/год
    profile = build_annual_profile(
        [100.0] * 40, period_days=30, horizon_years=3, base_annual_m3=1216.67
    )
    assert profile.horizon_years == 3
    for annual in profile.annual_m3:
        assert annual == pytest.approx(365 * 100.0 / 30, abs=0.01)  # abs — годовые округляются
    assert profile.extrapolated_tail is False


def test_build_annual_profile_flags_extrapolated_tail():
    # на 3 года при 30-суточных периодах нужно 37 периодов, дано 5
    profile = build_annual_profile(
        [100.0] * 5, period_days=30, horizon_years=3, base_annual_m3=1000.0
    )
    assert profile.extrapolated_tail is True
    assert len(profile.annual_m3) == 3


def test_build_annual_profile_follows_growing_forecast():
    growing = [100.0 + 10.0 * k for k in range(40)]
    profile = build_annual_profile(
        growing, period_days=30, horizon_years=3, base_annual_m3=1216.67
    )
    assert profile.annual_m3[0] < profile.annual_m3[1] < profile.annual_m3[2]


def test_build_annual_profile_validates_arguments():
    with pytest.raises(ValueError):
        build_annual_profile([1.0], period_days=0, horizon_years=1, base_annual_m3=1.0)
    with pytest.raises(ValueError):
        build_annual_profile([1.0], period_days=30, horizon_years=0, base_annual_m3=1.0)
    with pytest.raises(ValueError):
        build_annual_profile([], period_days=30, horizon_years=1, base_annual_m3=1.0)


def test_ratio_falls_back_to_one_without_base():
    profile = InjectionProfile(base_annual_m3=0.0, annual_m3=[500.0, 700.0])
    assert profile.ratios() == [1.0, 1.0]


# ───────────────────────── финансовые примитивы ─────────────────────────


def test_npv_discounts_future_flows():
    # 110 через год при ставке 10 % = 100 сегодня, минус CAPEX 100 → 0
    assert net_present_value(100.0, [110.0], 0.10) == pytest.approx(0.0, abs=1e-6)


def test_npv_without_discounting_is_plain_sum():
    assert net_present_value(50.0, [30.0, 30.0], 0.0) == pytest.approx(10.0)


def test_npv_rejects_impossible_rate():
    with pytest.raises(ValueError):
        net_present_value(100.0, [10.0], -1.0)


def test_irr_zeroes_the_npv():
    flows = [400.0, 400.0, 400.0]
    rate = internal_rate_of_return(1000.0, flows)
    assert rate is not None
    assert net_present_value(1000.0, flows, rate) == pytest.approx(0.0, abs=0.05)


def test_irr_is_none_without_capex_or_effect():
    assert internal_rate_of_return(0.0, [100.0, 100.0]) is None
    assert internal_rate_of_return(100.0, [0.0, 0.0]) is None


def test_irr_is_none_when_project_never_breaks_even():
    # 1 тыс. ₽ в год против CAPEX 10 000 — на любой ставке NPV < 0
    assert internal_rate_of_return(10_000.0, [1.0, 1.0, 1.0]) is None


def test_payback_interpolates_inside_the_year():
    # CAPEX 150 при 100/год: перекрытие в середине второго года → 1,5
    assert payback_from_cumulative([100.0, 200.0, 300.0], 150.0) == pytest.approx(1.5)


def test_payback_is_zero_without_capex_and_none_if_never():
    assert payback_from_cumulative([10.0], 0.0) == 0.0
    assert payback_from_cumulative([10.0, 20.0], 1000.0) is None


# ───────────────────────── ТЭО на горизонте ─────────────────────────


def test_flat_profile_reproduces_the_annual_estimate():
    """Без роста закачки эффект каждого года равен «плоской» годовой оценке."""
    measure = _measure(100_000.0, capex=1000.0)
    profile = InjectionProfile.flat(50_000.0, 3)
    ev = evaluate_horizon(measure, _FakeAudit(), profile, tariff=TARIFF, discount_rate=0.0)

    expected_year = 100_000.0 * TARIFF / 1000.0  # тыс. ₽/год
    assert [y.money_saving_krub for y in ev.years] == [pytest.approx(expected_year)] * 3
    assert ev.total_money_krub == pytest.approx(expected_year * 3)
    # при нулевой ставке дисконтированный поток совпадает с номинальным
    assert ev.total_discounted_krub == pytest.approx(ev.total_money_krub)


def test_growing_injection_raises_the_effect():
    measure = _measure(100_000.0, capex=1000.0)
    profile = InjectionProfile(base_annual_m3=1000.0, annual_m3=[1000.0, 1200.0, 1500.0])
    ev = evaluate_horizon(measure, _FakeAudit(), profile, tariff=TARIFF, discount_rate=0.0)

    assert [y.volume_ratio for y in ev.years] == [1.0, 1.2, 1.5]
    base = ev.years[0].money_saving_krub
    assert ev.years[1].money_saving_krub == pytest.approx(base * 1.2)
    assert ev.years[2].money_saving_krub == pytest.approx(base * 1.5)


def test_volume_exponent_changes_the_scaling_law():
    profile = InjectionProfile(base_annual_m3=1000.0, annual_m3=[2000.0])
    linear = evaluate_horizon(
        _measure(1000.0, exponent=1.0), _FakeAudit(), profile, tariff=TARIFF, discount_rate=0.0
    )
    cubic = evaluate_horizon(
        _measure(1000.0, exponent=3.0), _FakeAudit(), profile, tariff=TARIFF, discount_rate=0.0
    )
    flat = evaluate_horizon(
        _measure(1000.0, exponent=0.0), _FakeAudit(), profile, tariff=TARIFF, discount_rate=0.0
    )
    assert linear.years[0].energy_saving_kwh == pytest.approx(2000.0)
    assert cubic.years[0].energy_saving_kwh == pytest.approx(8000.0)
    assert flat.years[0].energy_saving_kwh == pytest.approx(1000.0)


def test_discounting_shrinks_later_years():
    measure = _measure(100_000.0, capex=1000.0)  # 400 тыс. ₽/год при TARIFF=4
    profile = InjectionProfile.flat(1000.0, 5)
    ev = evaluate_horizon(measure, _FakeAudit(), profile, tariff=TARIFF, discount_rate=0.15)

    factors = [y.discount_factor for y in ev.years]
    assert factors[0] > factors[1] > factors[2]
    assert ev.total_discounted_krub < ev.total_money_krub
    # дисконтированная окупаемость не может быть быстрее простой
    assert ev.discounted_payback_years > ev.payback_years


def test_discounted_payback_can_exceed_horizon_while_simple_one_fits():
    """Та же экономика на 3 года: без дисконта окупается, с дисконтом — нет."""
    measure = _measure(100_000.0, capex=1000.0)
    ev = evaluate_horizon(
        measure, _FakeAudit(), InjectionProfile.flat(1000.0, 3), tariff=TARIFF, discount_rate=0.15
    )
    assert ev.payback_years == pytest.approx(2.5)
    assert ev.discounted_payback_years is None


def test_falling_injection_can_push_payback_beyond_horizon():
    measure = _measure(100_000.0, capex=2000.0)  # 400 тыс. ₽ в первый год при TARIFF=4
    declining = InjectionProfile(base_annual_m3=1000.0, annual_m3=[1000.0, 500.0, 100.0])
    ev = evaluate_horizon(measure, _FakeAudit(), declining, tariff=TARIFF, discount_rate=0.15)

    assert ev.years[-1].money_saving_krub < ev.years[0].money_saving_krub
    assert ev.discounted_payback_years is None  # за 3 года CAPEX не перекрыт
    assert ev.npv_krub < 0


def test_measure_without_capex_pays_back_immediately():
    measure = _measure(50_000.0, capex=0.0, cls=MeasureClass.quick_win)
    ev = evaluate_horizon(
        measure, _FakeAudit(), InjectionProfile.flat(1000.0, 3), tariff=TARIFF
    )
    assert ev.payback_years == 0.0
    assert ev.discounted_payback_years == 0.0
    assert ev.irr is None
    assert ev.npv_krub > 0


def test_suggest_over_horizon_filters_and_sorts():
    catalog = [
        _measure(10_000.0, measure_id="small"),
        _measure(90_000.0, measure_id="big"),
        _measure(0.0, measure_id="zero"),
    ]
    evals = suggest_measures_over_horizon(
        _FakeAudit(),
        InjectionProfile.flat(1000.0, 3),
        tariff=TARIFF,
        catalog=catalog,
    )
    assert [e.measure_id for e in evals] == ["big", "small"]  # ноль отфильтрован


def test_horizon_length_follows_the_profile():
    ev = evaluate_horizon(
        _measure(1000.0), _FakeAudit(), InjectionProfile.flat(1000.0, 7), tariff=TARIFF
    )
    assert ev.horizon_years == 7
    assert [y.year for y in ev.years] == [1, 2, 3, 4, 5, 6, 7]
