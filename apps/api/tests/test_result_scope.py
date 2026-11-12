import pytest

from ppd_audit.core.audit import audit_aggregate
from ppd_audit.core.losses import build_loss_map
from ppd_audit.measures import suggest_measures
from ppd_audit.services.analysis import annual_summary, measure_analysis
from ppd_audit.services.result_scope import result_scope
from ppd_audit.spec import AggregateSpec, MotorSpec, PumpSpec, ReferenceOutputs, RegimeMeasurement


def _audit(*, runtime=None, reference_runtime=None, q_day=864.0, energy=4320.0):
    return audit_aggregate(
        AggregateSpec(
            id="A",
            pump=PumpSpec(q_nom=36, h_nom=1000, eta_nom=0.8),
            motor=MotorSpec(p_nom=200, eta_nom=0.9),
            regime=RegimeMeasurement(
                rho=1000,
                p_in=1,
                p_out=10,
                p_bg=9,
                q_fact=36,
                p_electric=180,
                q_day=q_day,
                t=24,
                w=energy,
                t_year=runtime,
            ),
            reference=ReferenceOutputs(t_year=reference_runtime),
        )
    )


def test_result_scope_marks_daily_kpi_as_fact_when_daily_energy_and_flow_exist():
    scope = result_scope(_audit(runtime=7200))
    assert scope.daily_kpi_is_fact is True
    assert scope.annual_runtime_is_assumed is False


def test_result_scope_marks_annual_estimate_as_scenario_when_runtime_is_missing():
    scope = result_scope(_audit())
    assert scope.daily_kpi_is_fact is True
    assert scope.annual_runtime_is_assumed is True


def test_result_scope_does_not_call_power_to_flow_ratio_a_daily_fact():
    scope = result_scope(_audit(runtime=7200, q_day=None, energy=None))
    assert scope.daily_kpi_is_fact is False


def test_result_scope_marks_pressure_snapshot_separately_from_daily_kpi():
    scope = result_scope(_audit(runtime=7200), daily_pressure_coverage_is_complete=False)
    assert scope.daily_kpi_is_fact is True
    assert scope.daily_pressure_coverage_is_complete is False


@pytest.mark.parametrize(
    ("runtime", "reference_runtime", "hours", "assumed"),
    [
        (None, None, 8760, True),
        (None, 4800, 4800, False),
        (6000, 4800, 6000, False),
        (0, 4800, 0, False),
        (None, 0, 0, False),
    ],
)
def test_annual_calculations_share_runtime_basis(runtime, reference_runtime, hours, assumed):
    audit = _audit(runtime=runtime, reference_runtime=reference_runtime)
    # This regime has 55 kW efficiency losses and 20 kW throttling losses.
    assert audit.dw_efficiency == pytest.approx(55 * hours)
    assert audit.dw_throttle == pytest.approx(20 * hours)
    scope = result_scope(audit)
    assert scope.annual_runtime_hours == hours
    assert scope.annual_runtime_is_assumed is assumed
    summary = annual_summary(audit, tariff=5)
    assert summary["efficiency_money_krub"] == pytest.approx(55 * hours * 5 / 1000)
    for item in build_loss_map(audit, tariff=5).items:
        assert item.annual_kwh == pytest.approx(item.power_kw * hours)
        assert item.annual_rub == pytest.approx(item.power_kw * hours * 5)
    measures = {item.measure_id: item for item in suggest_measures(audit, tariff=5)}
    if hours:
        assert measures["efficiency_recovery_scenario"].energy_saving_kwh == pytest.approx(
            55 * hours
        )
        assert measures["throttle_down"].energy_saving_kwh == pytest.approx(20 * hours)
    else:
        assert measures == {}
    forecast = measure_analysis(audit, scope, 5, None, basis="forecast")
    assert forecast["profile"]["base_annual_m3"] == pytest.approx(36 * hours)


def test_daily_sec_does_not_change_spot_regime_annual_losses():
    audit = _audit(runtime=4800, energy=8640)
    assert audit.sec_fact == pytest.approx(10)
    assert audit.dw_efficiency == pytest.approx(55 * 4800)
    forecast = measure_analysis(audit, result_scope(audit), 5, None, basis="forecast")
    assert forecast["setpoint"]["sec_current"] == pytest.approx(5)
