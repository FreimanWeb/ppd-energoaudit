from datetime import date

import pytest

from ppd_audit.config import project_root
from ppd_audit.db_seed import bootstrap_database


@pytest.fixture
def db(tmp_path):
    return bootstrap_database(tmp_path / "audit.sqlite", project_root() / "config/plants")


def test_confirmed_density_is_available_from_receipt_not_backfilled(db):
    assert db.plant_density_default("knsopu", date(2026, 10, 15)) is None
    assert db.plant_density_default("knsopu", date(2026, 10, 16))["density_kgm3"] == 1142
    assert db.plant("knsopu")["default_density"] == 1123
    from ppd_audit.services.catalog import get_field_trip_audit

    _, audit = get_field_trip_audit("knsopu", "НА-1", database=db)
    assert audit.regime.rho == 1142


def test_well_history_is_separate_and_import_is_idempotent(db, monkeypatch):
    row = {
        "plant_code": "kns54an",
        "well_code": "4623А",
        "observed_at": "2026-09-01",
        "grain": "month",
        "record_kind": "monthly_actual",
        "metric": "p_well",
        "value": 100,
        "unit": "атм",
        "study_type": "",
        "source_file": "source.xls",
        "source_sheet": "Динамика",
        "source_row": 6,
        "exported_at": "2026-10-14",
    }
    with db._connection() as c:
        before = c.execute("SELECT COUNT(*) FROM telemetry_measurements").fetchone()[0]
    db.add_well_measurements([row])
    db.add_well_measurements([row])
    assert db.wells("kns54an")[0]["code"] == "4623А"
    records = db.well_history("kns54an", "4623А")
    assert len(records) == 1
    assert records[0]["grain"] == "month"
    assert records[0]["unit"] == "атм"
    with db._connection() as c:
        assert c.execute("SELECT COUNT(*) FROM telemetry_measurements").fetchone()[0] == before
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ppd_audit.api import analysis_routes

    monkeypatch.setattr(analysis_routes, "_database", lambda: db)
    app = FastAPI()
    app.include_router(analysis_routes.router)
    client = TestClient(app)
    assert client.get("/objects/kns54an/wells").json()["wells"][0]["code"] == "4623А"
    response = client.get("/objects/kns54an/wells/4623А/history")
    assert response.status_code == 200
    assert response.json()["records"][0]["unit"] == "атм"
    assert response.json()["warnings"]
    assert client.get("/objects/kns54an/wells/missing/history").status_code == 404
    assert client.get("/objects/missing/wells").status_code == 404


def test_measured_density_takes_precedence_over_received_default(db):
    from datetime import datetime, timedelta

    from ppd_audit.services.telemetry_audit import build_regime

    for day, expected in [(15, 1123), (17, 1142)]:
        start = datetime(2026, 10, day)
        for metric, value, unit in [
            ("p_in", 1, "МПа"), ("p_out", 10, "МПа"),
            ("power", 300, "кВт"), ("flow_rate", 100, "м³/ч"),
        ]:
            db.add_measurement("knsopu", "НА-1", start, metric, value, unit)
        assert build_regime(
            db, "knsopu", "НА-1", start, start + timedelta(days=1),
            require_daily_pressure_coverage=False,
        ).rho == expected
    db.add_measurement("knsopu", "НА-1", start, "density", 1100, "кг/м³")
    assert build_regime(
        db, "knsopu", "НА-1", start, start + timedelta(days=1),
        require_daily_pressure_coverage=False,
    ).rho == 1100
