from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from ppd_audit.api.main import app
from ppd_audit.db import AuditDatabase
from ppd_audit.spec import load_object_spec


@pytest.fixture
def diagnostic_client(tmp_path, monkeypatch):
    from ppd_audit.api import analysis_routes, dashboard

    database = AuditDatabase(tmp_path / "diagnostics.sqlite")
    database.migrate()
    obj = load_object_spec("kns54an").model_copy(deep=True)
    database.upsert_plant(obj.id, obj.name, "НГДУ", "агрессивная", "кнс")
    for aggregate in obj.aggregates:
        database.upsert_aggregate(obj.id, aggregate.id, aggregate.role)
    monkeypatch.setattr(analysis_routes, "_database", lambda: database)
    monkeypatch.setattr(analysis_routes, "load_object_spec", lambda _: obj)
    monkeypatch.setattr(dashboard, "_database", lambda: database)
    return TestClient(app), obj, database


def view(client, object_id="kns54an", aggregate_id="НА-1"):
    result = client.post(f"/objects/{object_id}/aggregates/{aggregate_id}/field-trip-audit")
    assert result.status_code == 200, result.text
    data = result.json()
    assert "diagnostics" in data
    return data["diagnostics"]


def rules(report):
    return {item["id"]: item for item in report["rules"]}


def test_pressure_inversion_is_a_data_check_not_a_repair_instruction(diagnostic_client):
    client, obj, _ = diagnostic_client
    aggregate = obj.aggregate("НА-1")
    aggregate.regime.p_bg = aggregate.regime.p_out + 0.2
    report = view(client)
    result = rules(report)["pressure_order"]
    assert result["status"] == "triggered"
    assert result["category"] == "data_check"
    assert {item["key"]: item["value"] for item in result["evidence"]} == {
        "p_bg": pytest.approx(14.8),
        "p_out": pytest.approx(14.6),
    }
    assert result["source"]["artifact_id"] == "A-2026-023"
    assert result["source"]["cells"] == "A10:F10"
    assert rules(report)["motor_underload"]["status"] == "insufficient_data"
    response = client.post("/objects/kns54an/aggregates/НА-1/field-trip-audit")
    assert response.json()["quality"]["status"] == "unfit"
    assert response.json()["losses"] == []
    assert (
        client.post(
            "/objects/kns54an/aggregates/НА-1/measures", json={"source": "field_trip"}
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "pressure_delta, expected", [(0, "clear"), (-0.1, "clear"), (0.1, "triggered")]
)
def test_pressure_order_boundaries(diagnostic_client, pressure_delta, expected):
    client, obj, _ = diagnostic_client
    regime = obj.aggregate("НА-1").regime
    regime.p_bg = regime.p_out + pressure_delta
    assert rules(view(client))["pressure_order"]["status"] == expected


@pytest.mark.parametrize(
    "load, low, high",
    [
        (0.49, "triggered", "clear"),
        (0.5, "clear", "clear"),
        (1, "clear", "clear"),
        (1.01, "clear", "triggered"),
    ],
)
def test_motor_load_strict_boundaries(diagnostic_client, load, low, high):
    client, obj, _ = diagnostic_client
    aggregate = obj.aggregate("НА-1")
    aggregate.regime.p_electric = load * aggregate.motor.p_nom / aggregate.motor.eta_nom
    checks = rules(view(client))
    assert checks["motor_underload"]["status"] == low
    assert checks["motor_overload"]["status"] == high
    assert checks["motor_underload"]["evidence"][0]["value"] == pytest.approx(load)


def test_missing_bg_pressure_is_not_a_normal_pressure_check(diagnostic_client):
    client, obj, _ = diagnostic_client
    obj.aggregate("НА-1").regime.p_bg = None
    checks = rules(view(client))
    assert checks["pressure_order"]["status"] == "insufficient_data"
    assert checks["pressure_order"]["evidence"][0]["value"] is None


def test_model_change_does_not_reuse_old_aggregate_rules(diagnostic_client):
    client, obj, _ = diagnostic_client
    obj.aggregate("НА-1").pump.model = "ЦНС 180-1422(-1)"
    report = view(client)
    assert report["binding_status"] == "model_mismatch"
    assert all(rule["status"] == "pending_confirmation" for rule in report["rules"])


def test_unconfirmed_curves_and_working_zone_never_trigger_replacement(diagnostic_client):
    client, obj, _ = diagnostic_client
    aggregate = obj.aggregate("НА-2")
    aggregate.regime.q_fact = 150
    # Points alone do not establish source, approval or applicability of a passport curve.
    aggregate.pump.curve_qh = [[56, 5000], [80, 4900], [96, 4800]]
    checks = rules(view(client, aggregate_id="НА-2"))
    for rule_id in ("flow_low", "flow_high", "head_low", "head_high", "pump_efficiency_low"):
        assert checks[rule_id]["status"] == "pending_confirmation"
        assert checks[rule_id]["action"] == ""
    assert checks["flow_high"]["condition"] == "Q > 96 м³/ч"
    assert checks["flow_high"]["source"]["cells"] == "A26:F26"


def test_annual_assumption_is_not_a_verified_annual_loss(diagnostic_client):
    client, obj, _ = diagnostic_client
    obj.aggregate("НА-1").regime.t_year = None
    checks = rules(view(client))
    assert checks["annual_throttle_loss"]["status"] == "insufficient_data"
    assert checks["annual_efficiency_loss"]["status"] == "insufficient_data"


def test_unfit_inputs_block_operating_advice(diagnostic_client):
    client, obj, _ = diagnostic_client
    obj.aggregate("НА-1").regime.p_electric = 1
    checks = rules(view(client))
    assert checks["motor_underload"]["status"] == "insufficient_data"
    assert checks["motor_underload"]["action"] == ""


def test_day_rules_do_not_use_single_pressure_snapshot(diagnostic_client):
    client, _, database = diagnostic_client
    at = datetime(2026, 10, 1)
    database.add_passport(
        "kns54an",
        "НА-1",
        valid_from=datetime(2020, 1, 1),
        pump_model="ЦНС 180-1422(-2)",
        pump_kind="центробежный",
        pump_q_nom=180,
        pump_h_nom=1163.5,
        pump_eta_nom=0.73,
        motor_model="ЭД",
        motor_p_nom=1250,
        motor_eta_nom=0.965,
    )
    for metric, value, unit in [
        ("p_in", 2, "МПа"),
        ("p_out", 14, "МПа"),
        ("flow_rate", 100, "м³/ч"),
        ("power", 1000, "кВт"),
        ("q_day", 2400, "м³/сут"),
        ("runtime", 24, "ч"),
        ("energy", 24000, "кВт·ч"),
        ("density", 1138, "кг/м³"),
    ]:
        database.add_measurement("kns54an", "НА-1", at, metric, value, unit)
    database.add_measurement("kns54an", None, at, "p_bg", 13, "МПа")
    response = client.post(
        "/objects/kns54an/aggregates/НА-1/snapshot-audit",
        json={"day": "2026-10-01", "timestamp": at.isoformat()},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "diagnostics" in body
    checks = rules(body["diagnostics"])
    assert checks["daily_efficiency_high"]["status"] == "insufficient_data"
    assert checks["specific_energy_low"]["status"] == "insufficient_data"
    assert checks["pressure_order"]["status"] == "clear"


def test_field_trip_daily_energy_does_not_prove_comparable_pressure(diagnostic_client):
    client, obj, _ = diagnostic_client
    regime = obj.aggregate("НА-1").regime
    regime.w = 1000
    regime.q_day = 1000
    check = rules(view(client))["specific_energy_low"]
    assert check["status"] == "insufficient_data"
    assert check["action"] == ""


def test_kns97_numbering_conflict_does_not_bind_by_model_alone(diagnostic_client):
    client, obj, database = diagnostic_client
    obj.id = "kns97pren"
    aggregate = obj.aggregate("НА-1")
    aggregate.id = "НА-2 ПР"
    aggregate.pump.model = "ЦНС 40-1000(-2)"
    database.upsert_plant(obj.id, obj.name, "НГДУ", "пресная", "кнс")
    database.upsert_aggregate(obj.id, aggregate.id, "работа")
    report = view(client, obj.id, aggregate.id)
    assert report["binding_status"] == "pending_confirmation"
    assert all(rule["status"] == "pending_confirmation" for rule in report["rules"])
