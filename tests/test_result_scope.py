from ppd_audit.services.result_scope import result_scope
from ppd_audit.spec import RegimeMeasurement


def _regime(*, q_day: float | None = 2400.0, energy: float | None = 4800.0) -> RegimeMeasurement:
    return RegimeMeasurement(
        rho=1000.0,
        p_in=1.0,
        p_out=10.0,
        q_day=q_day,
        t=24.0,
        w=energy,
    )


def test_result_scope_marks_daily_kpi_as_fact_when_daily_energy_and_flow_exist():
    scope = result_scope(_regime(), annual_runtime=7200.0)

    assert scope.daily_kpi_is_fact is True
    assert scope.annual_runtime_hours == 7200.0
    assert scope.annual_runtime_is_assumed is False


def test_result_scope_marks_annual_estimate_as_8760_hour_scenario_when_runtime_is_missing():
    scope = result_scope(_regime(), annual_runtime=None)

    assert scope.daily_kpi_is_fact is True
    assert scope.annual_runtime_hours == 8760.0
    assert scope.annual_runtime_is_assumed is True


def test_result_scope_does_not_call_power_to_flow_ratio_a_daily_fact():
    scope = result_scope(_regime(q_day=None, energy=None), annual_runtime=7200.0)

    assert scope.daily_kpi_is_fact is False
