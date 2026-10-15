"""Network scenario controls preserve context and validate the HTTP boundary."""

import pytest
from pydantic import ValidationError

from ppd_audit.api.analysis_contracts import NetworkLossRequest


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ppd_audit.api import analysis_routes
    from ppd_audit.config import project_root
    from ppd_audit.db_seed import bootstrap_database

    db = bootstrap_database(tmp_path / "network.sqlite", project_root() / "config/plants")
    monkeypatch.setattr(analysis_routes, "_database", lambda: db)
    app = FastAPI()
    app.include_router(analysis_routes.router)
    return TestClient(app)


def test_network_request_accepts_only_known_interventions_and_signed_elevation():
    request = NetworkLossRequest.model_validate({
        "source": "field_trip",
        "intervention": "reduce_head",
        "scenario": {"elevation_change_m": -50},
    })
    assert request.intervention == "reduce_head"
    assert request.scenario.elevation_change_m == -50
    with pytest.raises(ValidationError):
        NetworkLossRequest.model_validate({"intervention": "invent_savings"})
    with pytest.raises(ValidationError):
        NetworkLossRequest.model_validate({"scenario": {"elevation_change_m": 1001}})


def test_network_api_recalculates_selected_measure_without_losing_context(client):
    path = "/objects/kns54an/aggregates/НА-1/network-losses"
    response = client.post(path, json={"source": "field_trip"})
    assert response.status_code == 200, response.text
    baseline = response.json()
    assert baseline["status"] == "scenario", baseline["warnings"]
    assert baseline["measures"]
    selected = baseline["measures"][0]["id"]
    response = client.post(path, json={"source": "field_trip", "intervention": selected})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["context"]["source"] == "field_trip"
    assert data["comparison"]["measure_id"] == selected
    assert data["comparison"]["before"]["input_kw"] == baseline["input_kw"]
    assert data["comparison"]["after"]["input_kw"] < baseline["input_kw"]
    assert abs(data["comparison"]["after"]["balance_error_kw"]) < 1e-7
    assert client.post(path, json={"intervention": "invent"}).status_code == 422
    assert client.post(path, json={"source": "telemetry"}).status_code == 400


def test_network_api_preserves_unavailable_and_unknown_object_guards(client):
    response = client.post(
        "/objects/kns25/aggregates/НА-1/network-losses", json={"source": "field_trip"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "unavailable"
    assert response.json()["measures"] == []
    assert response.json()["comparison"] is None
    assert client.post("/objects/missing/aggregates/NA/network-losses", json={}).status_code == 404
