"""Counterfactuals preserve useful delivery and close the physical power balance."""

from copy import deepcopy

import pytest

from ppd_audit.core.audit import audit_aggregate
from ppd_audit.services import network_losses
from ppd_audit.services.armits_data import load_network
from ppd_audit.spec import (
    AggregateSpec,
    Branch,
    MotorSpec,
    PumpSpec,
    RegimeMeasurement,
)


@pytest.fixture
def audit():
    return audit_aggregate(
        AggregateSpec(
            id="test",
            pump=PumpSpec(eta_nom=0.7, q_nom=100, h_nom=1000),
            motor=MotorSpec(p_nom=600, eta_nom=0.95),
            regime=RegimeMeasurement(
                rho=1000,
                p_in=0.2,
                p_out=10,
                p_bg=9,
                q_fact=100,
                p_electric=600,
                nu=1,
            ),
        ),
        Branch.kns,
    )


@pytest.fixture
def network():
    def segment(pid, origin, target, length):
        return {
            "id": pid,
            "pipeline_id": pid,
            "pipeline_name": pid,
            "purpose": "Напорный",
            "from_node": origin,
            "to_node": target,
            "start_m": 0,
            "end_m": length,
            "length_m": length,
            "outer_diameter_mm": 200,
            "wall_thickness_mm": 5,
            "source_sheet": "test",
            "source_row": 1,
        }

    return {
        "object_id": "kns54an",
        "segments": [
            segment("main", "КНС-54", "junction", 1000),
            segment("a", "junction", "скв. 1", 1000),
            segment("b", "junction", "скв. 2", 500),
        ],
        "wells": [{"id": "1"}, {"id": "2"}],
    }


@pytest.fixture
def options():
    return {"well_diameter_mm": 150, "local_resistance_k": 100}


def test_scenario_analysis_closes_balance_and_preserves_inputs(audit, network, options):
    original = deepcopy((audit, network, options))
    result = network_losses.build_network_analysis(audit, network, options)
    assert result["status"] == "scenario"
    assert result["balance_error_kw"] == pytest.approx(0, abs=1e-8)
    assert result["network"]["total_length_m"] == 2500
    assert result["comparison"] is None
    assert {m["id"] for m in result["measures"]} == {
        "reduce_head",
        "clean_pipes",
        "reduce_local_resistance",
    }
    savings = []
    for measure in result["measures"]:
        comparison = network_losses.build_network_analysis(
            audit,
            network,
            options,
            measure["id"],
        )["comparison"]
        assert comparison["before"]["useful_kw"] == comparison["after"]["useful_kw"]
        after = comparison["after"]
        assert after["balance_error_kw"] == pytest.approx(0, abs=1e-8)
        assert sum(item["power_kw"] for item in after["items"]) == pytest.approx(after["input_kw"])
        assert min(item["power_kw"] for item in after["items"]) >= -1e-8
        assert comparison["saving_kw"] > 0
        assert measure["assumptions"]
        savings.append(comparison["saving_kw"])
    assert len(set(savings)) == 3
    assert (audit, network, options) == original


def test_friction_reduction_without_head_control_only_moves_losses(audit, network, options):
    before = network_losses.build_network_loss_map(audit, network, options)
    after = network_losses.build_network_loss_map(audit, network, {**options, "roughness_mm": 0.05})
    assert after["input_kw"] == before["input_kw"]
    assert after["total_loss_kw"] == pytest.approx(before["total_loss_kw"])
    assert sum(w["choke_loss_kw"] for w in after["wells"]) > sum(
        w["choke_loss_kw"] for w in before["wells"]
    )


@pytest.mark.parametrize("height", [-100, 0, 100])
def test_signed_elevation_is_useful_work(audit, network, options, height):
    baseline = network_losses.build_network_loss_map(audit, network, options)
    result = network_losses.build_network_loss_map(
        audit, network, {**options, "elevation_change_m": height}
    )
    assert result["status"] == "scenario"
    assert result["useful_kw"] == pytest.approx(
        baseline["useful_kw"] + 1000 * 9.81 * height / 1e6 * audit.regime.q / 3.6
    )
    assert result["balance_error_kw"] == pytest.approx(0, abs=1e-8)


def test_negative_total_demand_is_unavailable(audit, network, options):
    result = network_losses.build_network_analysis(
        audit, network, {**options, "useful_pressure_mpa": 0, "elevation_change_m": -1}
    )
    assert result["status"] == "unavailable"
    assert result["measures"] == []


def test_invalid_and_inapplicable_interventions(audit, network, options):
    with pytest.raises(ValueError):
        network_losses.build_network_analysis(audit, network, options, "unknown")
    with pytest.raises(ValueError):
        network_losses.build_network_analysis(audit, network, {"unknown": 1})
    with pytest.raises(ValueError):
        network_losses.build_network_analysis(
            audit, network, {**options, "roughness_mm": 0}, "clean_pipes"
        )
    with pytest.raises(ValueError):
        network_losses.build_network_analysis(
            audit, network, {**options, "local_resistance_k": 0}, "reduce_local_resistance"
        )
    infeasible = network_losses.build_network_analysis(audit, network, {"useful_pressure_mpa": 100})
    assert infeasible["status"] == "infeasible"
    assert infeasible["measures"] == []
    assert infeasible["comparison"] is None
    with pytest.raises(ValueError):
        network_losses.build_network_analysis(
            audit, network, {"useful_pressure_mpa": 100}, "reduce_head"
        )


def test_no_surplus_head_has_no_head_measure(audit, network, options):
    network["segments"][-1]["length_m"] = 1000
    network["segments"][-1]["end_m"] = 1000
    initial = network_losses.build_network_loss_map(audit, network, options)
    required = max(w["required_pressure_mpa"] for w in initial["wells"])
    audit.decomposition.p_bg_useful = required * audit.regime.q / 3.6
    result = network_losses.build_network_analysis(audit, network, options)
    assert "reduce_head" not in {m["id"] for m in result["measures"]}
    with pytest.raises(ValueError):
        network_losses.build_network_analysis(audit, network, options, "reduce_head")


@pytest.mark.parametrize("value", [True, float("nan"), -1001, 1001, "10"])
def test_elevation_validation(audit, network, value):
    with pytest.raises(ValueError):
        network_losses.build_network_analysis(audit, network, {"elevation_change_m": value})


def test_unavailable_network_and_zero_flow(audit, network, options):
    network["object_id"] = "other"
    result = network_losses.build_network_analysis(audit, network, options)
    assert result["measures"] == []
    assert result["comparison"] is None
    network["object_id"] = "kns54an"
    audit.regime.q = 0
    assert network_losses.build_network_analysis(audit, network, options)["status"] == "unavailable"


def test_real_registry_geometry_supports_model_comparison(audit):
    network = load_network("kns54an")
    original = deepcopy(network)
    result = network_losses.build_network_analysis(audit, network)
    assert result["status"] == "scenario"
    assert result["network"]["well_count"] == 33
    assert result["network"]["total_length_m"] > 0
    assert result["measures"]
    for measure in result["measures"]:
        after = network_losses.build_network_analysis(
            audit,
            network,
            intervention=measure["id"],
        )["comparison"]["after"]
        assert after["balance_error_kw"] == pytest.approx(0, abs=1e-8)
        assert after["useful_kw"] == result["useful_kw"]
    assert network == original
