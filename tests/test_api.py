from importlib import import_module

from fastapi.testclient import TestClient

from ppd_audit.api.main import app, validate_telemetry_submission
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
