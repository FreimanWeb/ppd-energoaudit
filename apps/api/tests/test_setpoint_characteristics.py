"""Ограждения оптимизации уставок и мероприятий по характеристике насоса.

Уставка может быть «проверена» только по характеристике с подтверждённым
источником (модель + частота вращения совпадают с установленными). Отсутствующая,
неподтверждённая или несовместимая кривая → честный статус «предложение»/
«недостижимо»/«недоступно», без выдуманной частоты ПЧ и без экстраполяции.
"""

import pytest

from ppd_audit.config import load_constraints
from ppd_audit.core.audit import audit_aggregate
from ppd_audit.measures import suggest_measures
from ppd_audit.optimize import optimize_setpoint
from ppd_audit.spec import (
    AggregateSpec,
    MotorSpec,
    PumpCurveSource,
    PumpSpec,
    RegimeMeasurement,
)


_VERIFIED = PumpCurveSource(
    kind="manufacturer",
    reference="паспорт завода-изготовителя",
    model="ЦНС36-1000",
    speed_rpm=2950.0,
    frequency_hz=50.0,
    verified=True,
)
_ENGINEERING = PumpCurveSource(
    kind="engineering",
    reference="извлечено из расчётной книжки ОПУ",
    model="ЦНС36-1000",
    speed_rpm=2950.0,
    frequency_hz=50.0,
    verified=False,
)


def _pump(curve_source=None, curves=True, curve_qh=None):
    return PumpSpec(
        model="ЦНС36-1000",
        q_nom=36,
        h_nom=1000,
        eta_nom=0.8,
        n_rpm=2950.0,
        curve_qh=(curve_qh if curve_qh is not None else [[20, 1100], [36, 1000], [50, 800]])
        if curves
        else [],
        curve_qeta=[[20, 0.70], [36, 0.80], [50, 0.70]] if curves else [],
        curve_source=curve_source,
    )


def _audit(*, vfd=False, p_bg=9.0, **pump_kw):
    return audit_aggregate(
        AggregateSpec(
            id="A",
            pump=_pump(**pump_kw),
            motor=MotorSpec(p_nom=150, eta_nom=0.9),
            vfd=vfd,
            regime=RegimeMeasurement(
                rho=1000,
                p_in=1.0,
                p_out=10.81,  # H=1000 м при rho=1000
                p_bg=p_bg,
                q_fact=36.0,
                p_electric=98.1 / (0.8 * 0.9 * (0.97 if vfd else 1.0)),
                t_year=4800.0,
            ),
        )
    )


# ---------- частота ПЧ выдаётся только для агрегата с ПЧ ----------


def test_no_vfd_no_frequency_proposal_status():
    opt = optimize_setpoint(_audit(vfd=False, curve_source=_VERIFIED), load_constraints())
    assert opt.vfd_freq_hz is None
    assert opt.status == "proposal"
    assert any("ПЧ" in note for note in opt.notes)


# ---------- недоступная проверка по характеристике ----------


def test_missing_characteristic_blocks_validated_setpoint():
    opt = optimize_setpoint(_audit(vfd=True, curves=False), load_constraints())
    assert opt.vfd_freq_hz is None
    assert opt.status == "proposal"
    assert opt.within_constraints  # «в пределах ограничений» не означает «проверено»


def test_unverified_engineering_source_is_proposal_not_validated():
    opt = optimize_setpoint(_audit(vfd=True, curve_source=_ENGINEERING), load_constraints())
    assert opt.status == "proposal"
    assert opt.vfd_freq_hz is None
    assert opt.sec_optimal is None
    assert opt.saving_kwh_year is None


def test_verified_manufacturer_curve_validates_candidate_point():
    opt = optimize_setpoint(_audit(vfd=True, curve_source=_VERIFIED), load_constraints())
    assert opt.status == "validated"
    assert opt.vfd_freq_hz is not None
    assert 35.0 <= opt.vfd_freq_hz <= 50.0
    from ppd_audit.core.curves import eta_due, head_due

    r = opt.vfd_freq_hz / 50
    candidate_head = r * r * head_due(36 / r, _pump().curve_qh)
    assert candidate_head == pytest.approx(8e6 / (1000 * 9.81), rel=1e-7)
    assert opt.sec_optimal == pytest.approx(
        8 / (3.6 * 0.9 * 0.97 * eta_due(36 / r, _pump().curve_qeta))
    )
    assert opt.saving_kwh_year == pytest.approx((opt.sec_current - opt.sec_optimal) * 36 * 4800)


def test_out_of_range_working_point_is_not_validated():
    opt = optimize_setpoint(
        _audit(
            vfd=True,
            curve_qh=[[18, 1120], [24, 1080], [30, 1020]],
            curve_source=_VERIFIED,
        ),
        load_constraints(),
    )
    assert opt.status == "proposal"
    assert opt.vfd_freq_hz is None


def test_model_mismatched_source_is_not_validated():
    source = PumpCurveSource(
        kind="manufacturer",
        reference="паспорт другого насоса",
        model="ЦНС500-2400",
        speed_rpm=2950.0,
        verified=True,
    )
    opt = optimize_setpoint(_audit(vfd=True, curve_source=source), load_constraints())
    assert opt.status == "proposal"
    assert opt.vfd_freq_hz is None


def test_speed_mismatched_source_is_not_validated():
    source = PumpCurveSource(
        kind="manufacturer",
        reference="кривая на 2970 об/мин",
        model="ЦНС36-1000",
        speed_rpm=2970.0,
        verified=True,
    )
    opt = optimize_setpoint(_audit(vfd=True, curve_source=source), load_constraints())
    assert opt.status == "proposal"
    assert opt.vfd_freq_hz is None


# ---------- недостижимые/неопределённые цели ----------


def test_unreachable_target_below_min_frequency_is_infeasible():
    # p_БГ=3 МПа → требуемый напор ~204 м, недостижим даже при f_min=35 Гц.
    opt = optimize_setpoint(_audit(vfd=True, p_bg=3.0, curve_source=_VERIFIED), load_constraints())
    assert opt.status == "infeasible"
    assert opt.vfd_freq_hz is None


def test_missing_manifold_pressure_makes_setpoint_unavailable():
    opt = optimize_setpoint(_audit(p_bg=None), load_constraints())
    assert opt.status == "unavailable"
    assert opt.saving_kwh_year is None
    assert opt.vfd_freq_hz is None
    assert opt.optimal_p_out is None
    assert opt.within_constraints is None


def test_absent_throttling_reports_no_change():
    opt = optimize_setpoint(_audit(p_bg=10.81), load_constraints())  # p_БГ = p_вых
    assert opt.status == "no_change"
    assert opt.saving_kwh_year == pytest.approx(0.0)
    assert opt.vfd_freq_hz is None


# ---------- мероприятия: ограничение применимости не скрывается ----------


def test_unchecked_regime_changes_remain_scenarios_not_quick_wins():
    from ppd_audit.measures.registry import MeasureClass

    evals = {e.measure_id: e for e in suggest_measures(_audit())}
    assert evals["throttle_down"].cls == MeasureClass.scenario.value
    assert evals["vfd"].cls == MeasureClass.scenario.value


def test_infeasible_target_is_not_a_quick_win_even_with_verified_curves():
    from ppd_audit.measures.registry import MeasureClass

    evals = {
        e.measure_id: e for e in suggest_measures(_audit(vfd=True, p_bg=3, curve_source=_VERIFIED))
    }
    assert evals["throttle_down"].cls == MeasureClass.scenario.value


def test_unknown_reference_frequency_is_not_assumed_to_be_vfd_maximum():
    source = _VERIFIED.model_copy(update={"frequency_hz": None})
    opt = optimize_setpoint(_audit(vfd=True, curve_source=source), load_constraints())
    assert opt.status == "proposal"
    assert opt.vfd_freq_hz is None


def test_no_change_does_not_override_known_pressure_violation():
    constraints = load_constraints().model_copy(
        update={"pressure_limits": {"pump_discharge_max": 8}}
    )
    opt = optimize_setpoint(_audit(p_bg=10), constraints)
    assert opt.status == "infeasible"
    assert opt.within_constraints is False


def test_pending_characteristic_does_not_predict_target_consumption():
    opt = optimize_setpoint(_audit(vfd=True), load_constraints())
    assert opt.status == "proposal"
    assert opt.vfd_freq_hz is None
    assert opt.sec_optimal is None
    assert opt.saving_kwh_year is None


def test_reference_inconsistent_with_measured_regime_cannot_validate_setpoint():
    baseline = _audit(vfd=True, curve_source=_VERIFIED)
    measured = baseline.spec.regime.model_copy(update={"p_out": 10.0, "p_electric": 180.0})
    result = audit_aggregate(baseline.spec.model_copy(update={"regime": measured}))
    opt = optimize_setpoint(result, load_constraints())
    assert opt.status == "proposal"
    assert opt.vfd_freq_hz is None
    assert opt.sec_optimal is None
    assert opt.saving_kwh_year is None


def test_ambiguous_speed_branch_is_not_declared_unreachable_or_validated():
    result = _audit(vfd=True, curve_source=_VERIFIED, curve_qh=[[20, 2000], [36, 1000], [50, 1500]])
    opt = optimize_setpoint(result, load_constraints())
    assert opt.status == "proposal"
    assert opt.vfd_freq_hz is None
    assert opt.saving_kwh_year is None
