"""Характеризация расчётных представлений перед отделением от Streamlit."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from ppd_audit.services.analysis import (
    pump_qh_curve as _pump_qh_curve,
    system_curve as _system_curve,
)
from ppd_audit.services.audit import run_energy_audit
from ppd_audit.services.result_scope import result_scope
from ppd_audit.spec import PumpKind, PumpSpec, load_object_spec


def test_existing_model_curves_characterization():
    p = PumpSpec(q_nom=100, h_nom=1000)
    q, h, passport = _pump_qh_curve(p)
    assert not passport
    assert len(q) == 41
    assert h[0] == 1220
    assert h[-1] == pytest.approx(725)
    qs, hs = _system_curve(100, 1000, 1, None, 1000, 100)
    assert hs[0] == 350
    assert hs[-1] == pytest.approx(1812.5)
    assert (
        _pump_qh_curve(PumpSpec(kind=PumpKind.positive_displacement, q_nom=100, h_nom=1000)) is None
    )


def test_pure_curves_preserve_legacy_models():
    from ppd_audit.services import analysis

    assert hasattr(analysis, "working_point"), "pure working-point view is missing"
    p = PumpSpec(q_nom=100, h_nom=1000, eta_nom=0.8)
    audit = SimpleNamespace(
        spec=SimpleNamespace(
            pump=p,
            regime=SimpleNamespace(flow=lambda: 100, p_in=1, p_bg=None, rho=1000),
            reference=None,
        ),
        regime=SimpleNamespace(h_fact=1000, eta_unit=0.65),
        h_due=None,
        eta_pump=None,
    )
    view = analysis.working_point(audit)
    assert view["origin"] == {"qh": "model", "qeta": "model", "system": "model"}
    assert len(view["qh"]) == 41
    assert view["qh"][-1]["h"] == pytest.approx(725)
    assert view["system"][0]["h"] == 350
    assert view["qeta"][0]["eta"] == pytest.approx(0.8 * (1 - 0.9 * 0.8**2))
    assert view["notes"]
    assert view["point"]["eta_pump"] is None
    assert view["point"]["eta"] == 0.65
    audit.eta_pump = 0.78
    view = analysis.working_point(audit)
    assert view["point"]["eta_pump"] == 0.78
    assert view["point"]["eta"] == 0.65


def test_measures_flat_fallback_and_unfit_guard():
    from ppd_audit.services import analysis

    assert hasattr(analysis, "measure_analysis"), "pure measures orchestration is missing"
    obj = load_object_spec("kns25")
    audit = run_energy_audit(obj)
    scope = result_scope(audit.spec.regime, audit.spec.regime.t_year)
    view = analysis.measure_analysis(audit, scope, 4.68, None, horizon_years=3, basis="forecast")
    assert view["profile"]["method"] == "flat"
    assert len(view["profile"]["annual_m3"]) == 3
    assert view["profile"]["base_annual_m3"] == audit.regime.q * scope.annual_runtime_hours
    assert view["horizon"]
    with pytest.raises(ValueError, match="непригоден"):
        analysis.measure_analysis(
            audit, scope, 4.68, None, quality=SimpleNamespace(allows_economic_conclusions=False)
        )


def test_onboarding_allows_passport_without_regime():
    from ppd_audit.services import analysis

    assert hasattr(analysis, "onboarding"), "shared readiness view is missing"
    spec = load_object_spec("kns25").aggregates[0].model_copy(update={"regime": None})
    view = analysis.onboarding(spec)
    assert len(view["telemetry_requirements"]) == 14
    assert not next(c for c in view["checks"] if c["field"] == "Телеметрия: p_вх")["present"]
    assert view["yaml_template"].startswith("# config/plants/")


def test_shared_loss_components_match_streamlit():
    from tabs.common import loss_components

    from ppd_audit.services import analysis

    assert hasattr(analysis, "loss_components"), "shared decomposition view is missing"
    for object_id in ["kns25", "dns7s"]:
        audit = run_energy_audit(load_object_spec(object_id))
        assert analysis.loss_components(audit) == loss_components(audit)


def test_volumetric_no_model_diagnostics_and_passport_precedence():
    from ppd_audit.services.analysis import working_point

    audit = run_energy_audit(load_object_spec("kns25"))
    audit.spec.pump.kind = PumpKind.positive_displacement
    audit.spec.pump.curve_qh = []
    audit.spec.pump.curve_qeta = []
    view = working_point(audit)
    assert view["qh"] == view["qeta"] == view["system"] == []
    assert view["nominal"] == {"q": None, "h": None, "eta": None}
    audit.spec.pump.curve_qh = [[0, 100], [1, 80]]
    assert working_point(audit)["origin"]["qh"] == "passport"


@pytest.mark.parametrize(
    "actual,nominal,name",
    [
        (0.73, 0.8, "норма"),
        (0.64, 0.8, "пониженный КПД"),
        (0.5, 0.8, "низкий КПД"),
        (0.5, None, "норма"),
    ],
)
def test_shared_pump_assessment_preserves_legacy_thresholds(actual, nominal, name):
    from ppd_audit.services import analysis

    assert hasattr(analysis, "efficiency_assessment")
    assert analysis.efficiency_assessment(actual, nominal)["name"] == name
