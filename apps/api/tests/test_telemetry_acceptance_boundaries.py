from datetime import datetime

from fastapi.testclient import TestClient

from ppd_audit.api.main import app
from ppd_audit.db import AuditDatabase
from ppd_audit.services.telemetry_acceptance import acceptance_report


def test_conflicting_same_time_readings_cannot_complete_a_regime():
    values = [
        ("p_in", 2, "МПа"),
        ("p_out", 14, "МПа"),
        ("power", 1000, "кВт"),
        ("flow_rate", 100, "м³/ч"),
        ("density", 1000, "кг/м³"),
    ]
    rows = [
        {"metric": m, "value": v, "unit": u, "timestamp": "2026-10-01T12:00:00"}
        for m, v, u in values
    ]
    assert acceptance_report(rows)["calculations"][1]["status"] == "available"
    rows.append({"metric": "p_out", "value": 15, "unit": "МПа", "timestamp": "2026-10-01T12:00:00"})
    assert acceptance_report(rows)["calculations"][1]["status"] == "blocked"


def test_acceptance_api_excludes_outside_window_and_other_aggregate(tmp_path, monkeypatch):
    from ppd_audit.api import data_routes

    database = AuditDatabase(tmp_path / "intake.sqlite")
    database.migrate()
    database.upsert_plant("plant", "КНС", "НГДУ", "пресная", "кнс")
    for code in ("A", "B"):
        database.upsert_aggregate("plant", code, "работающий")
    database.add_measurement("plant", "A", datetime(2026, 9, 30), "energy", 100, "кВт·ч")
    database.add_measurement("plant", "A", datetime(2026, 10, 1), "q_day", 50, "м³/сут")
    database.add_measurement("plant", "B", datetime(2026, 10, 1), "energy", 100, "кВт·ч")
    monkeypatch.setattr(data_routes, "_database", lambda: database)
    client = TestClient(app)
    url = "/objects/plant/telemetry-acceptance?aggregate_id=A&start=2026-10-01&end=2026-10-01"
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["calculations"][0]["status"] == "blocked"
    energy = next(s for s in response.json()["signals"] if s["metric"] == "energy")
    assert energy["records"] == 0
    assert client.get(url.replace("end=2026-10-01", "end=2026-09-01")).status_code == 400
    assert client.get(url.replace("aggregate_id=A", "aggregate_id=missing")).status_code == 404
