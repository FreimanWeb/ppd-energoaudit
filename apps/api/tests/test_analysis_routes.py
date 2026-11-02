from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ppd_audit.db import AuditDatabase
from ppd_audit.services.manual_data import passport_fields_from_equipment
from ppd_audit.spec import EquipmentData


@pytest.fixture
def analysis_client(tmp_path, monkeypatch):
    from ppd_audit.api import analysis_routes

    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("kns25", "КНС-25", "НГДУ", "пресная", "кнс")
    from ppd_audit.spec import load_object_spec

    agg = load_object_spec("kns25").aggregates[0]
    db.upsert_aggregate("kns25", agg.id, "работа")
    db.add_passport(
        "kns25",
        agg.id,
        valid_from=datetime(1900, 1, 1),
        **passport_fields_from_equipment(
            EquipmentData.model_construct(
                pump=agg.pump,
                motor=agg.motor,
                transmission=agg.transmission,
                vfd=agg.vfd,
            )
        ),
    )
    monkeypatch.setattr(analysis_routes, "_database", lambda: db)
    app = FastAPI()
    app.include_router(analysis_routes.router)
    return TestClient(app), agg.id


def test_analysis_field_trip_and_economics(analysis_client):
    client, agg = analysis_client
    base = f"/objects/kns25/aggregates/{agg}"
    view = client.post(base + "/field-trip-audit", json={})
    assert view.status_code == 200, view.text
    data = view.json()
    assert data["source"] == "field_trip"
    assert data["snapshot"] is None
    assert data["passport"]["pump"]["model"]
    assert data["sources"]
    point = client.post(base + "/working-point", json={"source": "field_trip"})
    assert point.status_code == 200, point.text
    assert point.json()["point"]["q"] > 0
    measures = client.post(base + "/measures", json={"source": "field_trip", "basis": "forecast"})
    assert measures.status_code == 200, measures.text
    assert len(measures.json()["profile"]["annual_m3"]) == 3
    assert client.get(base + "/onboarding").status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"source": "telemetry"},
        {"source": "telemetry", "day": "20260724", "timestamp": "2026-07-24T00:00:00"},
        {"source": "telemetry", "day": "2026-07-24", "timestamp": "2026-07-24T00:00:00+03:00"},
        {"source": "telemetry", "day": "2026-07-24", "timestamp": "2026-07-25T00:00:00"},
    ],
)
def test_analysis_rejects_missing_or_invalid_context(analysis_client, payload):
    client, agg = analysis_client
    assert (
        client.post(f"/objects/kns25/aggregates/{agg}/working-point", json=payload).status_code
        == 400
    )


def test_unknown_analysis_ids_404(analysis_client):
    client, _ = analysis_client
    assert (
        client.post("/objects/missing/aggregates/missing/field-trip-audit", json={}).status_code
        == 404
    )


def test_field_trip_unfit_preserves_inputs_but_no_economic_outputs(analysis_client, monkeypatch):
    from ppd_audit.api import analysis_routes
    from ppd_audit.spec import load_object_spec

    obj = load_object_spec("kns25").model_copy(deep=True)
    client, agg = analysis_client
    spec = obj.aggregate(agg)
    spec.regime.w = 1
    spec.regime.p_electric = 1
    monkeypatch.setattr(analysis_routes, "load_object_spec", lambda _: obj)
    base = f"/objects/kns25/aggregates/{agg}"
    view = client.post(base + "/field-trip-audit").json()
    assert view["quality"]["status"] == "unfit"
    assert view["losses"] == []
    assert view["regime"]["rho"] == spec.regime.rho
    assert client.post(base + "/measures", json={"source": "field_trip"}).status_code == 400


def test_onboarding_db_only_object_without_date(tmp_path, monkeypatch):
    from datetime import datetime

    from ppd_audit.api import analysis_routes

    db = AuditDatabase(tmp_path / "db-only.sqlite")
    db.migrate()
    db.upsert_plant("db_only", "Без YAML", "НГДУ", "пресная", "кнс")
    db.upsert_aggregate("db_only", "НА-1", "работа")
    db.add_passport(
        "db_only",
        "НА-1",
        valid_from=datetime(2020, 1, 1),
        pump_model="ЦНС",
        pump_kind="центробежный",
        motor_model="ЭД",
        pump_q_nom=100,
        pump_h_nom=1000,
        pump_eta_nom=0.8,
        motor_p_nom=500,
        motor_eta_nom=0.95,
    )
    monkeypatch.setattr(analysis_routes, "_database", lambda: db)
    app = FastAPI()
    app.include_router(analysis_routes.router)
    response = TestClient(app).get("/objects/db_only/aggregates/НА-1/onboarding")
    assert response.status_code == 200, response.text
    checks = response.json()["checks"]
    assert not next(c for c in checks if c["field"] == "Телеметрия: p_вх")["present"]
