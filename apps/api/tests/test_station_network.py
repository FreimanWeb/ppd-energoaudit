from copy import deepcopy
from dataclasses import replace

import pytest

from ppd_audit.config import load_plant
from ppd_audit.core.audit import audit_aggregate
from ppd_audit.core.hydraulics import darcy_weisbach_dp
from ppd_audit.services.demo import demo_network
from ppd_audit.services.station_network import build_station_network


@pytest.fixture
def audits():
    return [audit_aggregate(aggregate) for aggregate in load_plant("demo-ppd").aggregates]


def test_station_balance_uses_total_flow_once_without_mutating_audits(audits):
    audits[1].eta_motor_real = 0.9
    audits[1].spec.transmission.efficiency = 0.95
    original = deepcopy(audits)
    network = demo_network()
    result = build_station_network(audits, network)
    assert result["status"] == "scenario"
    assert result["input_kw"] == sum(a.regime.p_electric for a in audits)
    assert result["input_kw"] - result["useful_kw"] - result["total_loss_kw"] == pytest.approx(0)
    assert result["balance_error_kw"] == pytest.approx(0)
    assert len(result["segments"]) == len(network["segments"])
    assert len(result["wells"]) == 6
    flow = sum(a.regime.q for a in audits)
    assert sum(w["flow_m3h"] for w in result["wells"]) == pytest.approx(flow)
    main = next(segment for segment in result["segments"] if segment["id"] == "main")
    assert main["flow_m3h"] == pytest.approx(flow)
    expected = darcy_weisbach_dp(flow, 1000, 0.19, 0.0001, 1000, 1) * flow / 3.6
    assert main["power_kw"] == pytest.approx(expected)
    parts = {part["name"]: part["power_kw"] for part in result["items"]}
    assert parts["Потери ЭД"] == pytest.approx(
        sum(a.regime.p_electric * 0.97 * (1 - a.eta_motor_real) for a in audits)
    )
    assert parts["Потери передачи"] == pytest.approx(
        sum(
            a.regime.p_electric * 0.97 * a.eta_motor_real * (1 - a.spec.transmission.efficiency)
            for a in audits
        )
    )
    assert audits == original
    assert "выбранный агрегат" not in str(result).lower()
    assert "выбранного агрегата" not in str(result).lower()
    assert "одного агрегата" not in str(result).lower()


def test_operator_graph_follows_report_groups_and_closes_at_the_wellheads(audits):
    result = build_station_network(audits, demo_network())
    graph = result["operator_balance"]
    assert graph["boundary"] == "wellhead_after_choke"
    assert graph["input_kw"] == result["input_kw"]
    hall, pipes, wells = graph["groups"]
    assert [group["id"] for group in graph["groups"]] == ["hall", "pipes", "wells"]
    assert [item["id"] for item in hall["children"]] == ["nominal", "efficiency", "pump_bg"]
    assert hall["children"][0]["power_kw"] == pytest.approx(
        sum(audit.decomposition.dp_nominal for audit in audits)
    )
    assert hall["children"][1]["power_kw"] == pytest.approx(
        sum(audit.decomposition.dp_efficiency for audit in audits)
    )
    assert hall["children"][2]["power_kw"] == pytest.approx(
        sum(audit.decomposition.dp_throttle for audit in audits)
    )
    assert [item["id"] for item in pipes["children"]] == ["friction", "local"]
    assert [item["id"] for item in wells["children"]] == ["choke"]
    for group in graph["groups"]:
        assert group["power_kw"] == pytest.approx(
            sum(item["power_kw"] for item in group["children"])
        )
    assert graph["bg_kw"] == pytest.approx(graph["input_kw"] - hall["power_kw"])
    assert graph["input_kw"] == pytest.approx(graph["total_loss_kw"] + graph["output_kw"])
    bore = next(
        item["power_kw"] for item in result["items"] if item["name"] == "Трение в стволах скважин"
    )
    assert graph["output_kw"] == pytest.approx(result["useful_kw"] + bore)


@pytest.mark.parametrize(
    "field,value",
    [
        ("p_in", 0.6),
        ("p_out", 11),
        ("p_bg", 9),
        ("rho", 1100),
        ("p_bg", None),
        ("p_out", float("nan")),
        ("q", 0),
        ("p_electric", None),
    ],
)
def test_incompatible_or_incomplete_station_is_unavailable(audits, field, value):
    audits[1].regime = replace(audits[1].regime, **{field: value})
    result = build_station_network(audits, demo_network())
    assert result["status"] == "unavailable"
    assert result["items"] == []
    assert result["input_kw"] is None
    assert result["operator_balance"] is None
    assert result["warnings"]


def test_missing_audits_and_duplicate_pumps_are_unavailable(audits):
    for values in ([], [audits[0], audits[0]]):
        result = build_station_network(values, demo_network())
        assert result["status"] == "unavailable"
        assert result["warnings"]


@pytest.mark.parametrize("field,value", [("nu", None), ("nu", 2)])
def test_incomplete_or_different_fluid_is_unavailable(audits, field, value):
    setattr(audits[1].spec.regime, field, value)
    assert build_station_network(audits, demo_network())["status"] == "unavailable"


def test_incompatible_vfd_and_invalid_efficiencies_are_unavailable(audits):
    audits[1].spec.vfd = False
    assert build_station_network(audits, demo_network())["status"] == "unavailable"
    audits[1].spec.vfd = True
    audits[1].eta_motor_real = 1.1
    assert build_station_network(audits, demo_network())["status"] == "unavailable"
