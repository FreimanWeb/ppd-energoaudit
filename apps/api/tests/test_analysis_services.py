"""Характеризация расчётных представлений сервисного слоя."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

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


def test_measures_flat_fallback_and_unfit_guard():
    from ppd_audit.services import analysis

    assert hasattr(analysis, "measure_analysis"), "pure measures orchestration is missing"
    obj = load_object_spec("kns25")
    audit = run_energy_audit(obj)
    scope = result_scope(audit)
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

    spec = load_object_spec("kns25").aggregates[0].model_copy(update={"regime": None})
    view = analysis.onboarding(spec)
    assert not next(c for c in view["checks"] if c["field"] == "Телеметрия: p_вх")["present"]


def test_loss_components_decompose_power_for_both_topologies():
    from ppd_audit.services import analysis

    for object_id in ["kns25", "dns7s"]:
        audit = run_energy_audit(load_object_spec(object_id))
        useful, components = analysis.loss_components(audit)
        assert useful > 0
        assert all(isinstance(label, str) and power >= 0 for label, power in components)


@pytest.mark.parametrize("object_id", ["kns129ln", "kns138ln", "kns175"])
def test_example_objects_are_marked_in_specs(object_id):
    assert load_object_spec(object_id).is_example


def test_volumetric_does_not_invent_centrifugal_curves():
    from ppd_audit.services.analysis import working_point

    audit = run_energy_audit(load_object_spec("kns25"))
    audit.spec.pump.kind = PumpKind.positive_displacement
    audit.spec.pump.curve_qh = []
    audit.spec.pump.curve_qeta = []
    view = working_point(audit)
    assert view["qh"] == view["qeta"] == view["system"] == []
    assert view["nominal"] == {"q": None, "h": None, "eta": None}
