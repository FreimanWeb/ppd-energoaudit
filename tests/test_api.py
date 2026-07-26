from datetime import datetime
from importlib import import_module

from fastapi.testclient import TestClient

from ppd_audit.api.main import app, validate_telemetry_submission
from ppd_audit.db import AuditDatabase
from ppd_audit.spec import load_object_spec
from ppd_audit.telemetry import TelemetrySubmission


def test_api_contracts_are_owned_by_api_package():
    contracts = import_module("ppd_audit.api.contracts")

    assert contracts.EnergyAuditRequest.__name__ == "EnergyAuditRequest"


def test_energy_audit_endpoint_uses_object_spec_contract():
    spec = load_object_spec("dns7s")
    client = TestClient(app)

    response = client.post(
        "/energy/audit",
        json={"object": spec.model_dump(mode="json"), "aggregate_id": "Н-4"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["object_id"] == "dns7s"
    assert body["aggregate_id"] == "Н-4"
    assert body["metrics"]["sec_fact_kwh_m3"] > 0


def test_telemetry_validate_endpoint_returns_normalized_input():
    submission = TelemetrySubmission.model_validate({
        "object_id": "dns7s",
        "technical_place": "КНС-85",
        "aggregation_period": "day",
        "records": [
            {
                "timestamp": "2026-07-12T00:00:00",
                "aggregate_id": "Н-4",
                "metric": "p_in",
                "unit": "МПа",
                "value": 1.2,
            },
            {
                "timestamp": "2026-07-12T00:00:00",
                "aggregate_id": "Н-4",
                "metric": "p_out",
                "unit": "МПа",
                "value": 9.8,
            },
            {
                "timestamp": "2026-07-12T00:00:00",
                "aggregate_id": "Н-4",
                "metric": "q_day",
                "unit": "м³/сут",
                "value": 2400,
            },
            {
                "timestamp": "2026-07-12T00:00:00",
                "aggregate_id": "Н-4",
                "metric": "runtime",
                "unit": "ч",
                "value": 24,
            },
            {
                "timestamp": "2026-07-12T00:00:00",
                "aggregate_id": "Н-4",
                "metric": "energy",
                "unit": "кВт·ч/сут",
                "value": 4800,
            },
            {
                "timestamp": "2026-07-12T00:00:00",
                "aggregate_id": "Н-4",
                "metric": "density",
                "unit": "кг/м³",
                "value": 1000,
            },
        ],
    })

    response = validate_telemetry_submission(submission)

    assert "/telemetry/validate" in {route.path for route in app.routes}
    assert response.validation.ok is True
    assert response.normalized_by_aggregate["Н-4"].q_day == 2400
    assert response.normalized_by_aggregate["Н-4"].t == 24


def test_objects_endpoint_returns_ngdu_from_database(tmp_path, monkeypatch):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("kns97", "КНС-97", "Елховнефть", "пресная", "кнс")
    monkeypatch.setenv("PPD_DATABASE_PATH", str(db.path))

    response = TestClient(app).get("/objects")

    assert response.status_code == 200
    assert response.json() == [
        {
            "code": "kns97",
            "name": "КНС-97",
            "ngdu_name": "Елховнефть",
            "water_type": "пресная",
            "branch": "кнс",
            "is_example": False,
        }
    ]


def test_telemetry_endpoint_persists_time_series(tmp_path, monkeypatch):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("kns97", "КНС-97", "Елховнефть", "пресная", "кнс")
    db.upsert_aggregate("kns97", "НА-02", "работа")
    monkeypatch.setenv("PPD_DATABASE_PATH", str(db.path))

    response = TestClient(app).post(
        "/telemetry",
        json={
            "object_id": "kns97",
            "technical_place": "main",
            "aggregation_period": "day",
            "records": [
                {
                    "timestamp": "2026-07-12T00:00:00",
                    "aggregate_id": "НА-02",
                    "metric": "p_in",
                    "unit": "МПа",
                    "value": 1.2,
                },
                {
                    "timestamp": "2026-07-12T00:00:00",
                    "aggregate_id": "НА-02",
                    "metric": "energy",
                    "unit": "кВт·ч/сут",
                    "value": 4800,
                },
            ],
        },
    )

    assert response.status_code == 201
    assert response.json() == {"stored": 2}
    assert [(row["metric"], row["unit"]) for row in db.measurements("kns97", "НА-02")] == [
        ("p_in", "МПа"),
        ("energy", "кВт·ч"),
    ]


def test_telemetry_audit_endpoint_uses_persisted_window(tmp_path, monkeypatch):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("kns97", "КНС-97", "Елховнефть", "пресная", "кнс")
    db.upsert_aggregate("kns97", "НА-02", "работа")
    db.add_passport(
        "kns97",
        "НА-02",
        valid_from=datetime(2020, 1, 1),
        pump_model="ЦНС 40-1000(-2)",
        pump_kind="центробежный",
        pump_q_nom=40.0,
        pump_h_nom=1000.0,
        pump_eta_nom=0.52,
        motor_model="ВАО2-450LB-2У2",
        motor_p_nom=400.0,
        motor_eta_nom=0.949,
    )
    at = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 210.0, "кВт"),
        ("q_day", 2400.0, "м³/сут"),
        ("runtime", 24.0, "ч"),
        ("density", 1000.0, "кг/м³"),
    ]:
        db.add_measurement("kns97", "НА-02", at, metric, value, unit)
    monkeypatch.setenv("PPD_DATABASE_PATH", str(db.path))

    response = TestClient(app).post(
        "/objects/kns97/aggregates/%D0%9D%D0%90-02/audits",
        json={"start": "2026-07-24T00:00:00", "end": "2026-07-25T00:00:00"},
    )

    assert response.status_code == 200
    assert response.json()["aggregate_id"] == "НА-02"
