"""Давления всех ветвей схемы относятся к одному точному моменту."""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ppd_audit.api.main import app
from ppd_audit.db import AuditDatabase


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from tabs import scheme


@pytest.fixture
def branch_database(tmp_path, monkeypatch):
    db = AuditDatabase(tmp_path / "branches.sqlite")
    db.migrate()
    db.upsert_plant("branches", "КНС", "НГДУ", "пресная", "кнс")
    timestamp = datetime(2025, 6, 1, 10)
    for index in range(1, 5):
        aggregate = f"НА-{index}"
        db.upsert_aggregate("branches", aggregate, "работа")
        if index == 4:
            continue
        # Давления действуют с предыдущего изменения, как в существующем ядре.
        for metric, value in (("p_in", index), ("p_out", index + 10)):
            db.add_measurement(
                "branches", aggregate, timestamp - timedelta(hours=1), metric, value, "МПа"
            )
        db.add_measurement(
            "branches",
            aggregate,
            timestamp + timedelta(seconds=index == 3),
            "power",
            210,
            "кВт",
        )
    monkeypatch.setenv("PPD_DATABASE_PATH", str(db.path))
    return db, timestamp


def test_legacy_all_branch_pressure_labels_characterization(branch_database, monkeypatch):
    db, timestamp = branch_database
    monkeypatch.setattr(scheme.lib, "database", lambda: db)
    ctx = SimpleNamespace(
        snapshot_timestamp=timestamp,
        object_id="branches",
        obj=SimpleNamespace(aggregates=[SimpleNamespace(id=f"НА-{i}") for i in range(1, 5)]),
    )
    assert scheme._aggregate_pressure_labels(ctx) == {
        "НА-1": ("p_вх=1,00 МПа", "p_вых=11,00 МПа"),
        "НА-2": ("p_вх=2,00 МПа", "p_вых=12,00 МПа"),
        "НА-3": (None, None),
        "НА-4": (None, None),
    }


def test_scheme_pressure_api_uses_same_exact_moment_for_every_branch(branch_database):
    _, timestamp = branch_database
    response = TestClient(app).get(
        "/objects/branches/scheme-pressures",
        params={"day": "2025-06-01", "timestamp": timestamp.isoformat()},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "НА-1": {"p_in_mpa": 1.0, "p_out_mpa": 11.0},
        "НА-2": {"p_in_mpa": 2.0, "p_out_mpa": 12.0},
    }


def test_scheme_pressure_api_does_not_substitute_nearby_snapshot(branch_database):
    _, timestamp = branch_database
    client = TestClient(app)
    response = client.get(
        "/objects/branches/scheme-pressures",
        params={"day": "2025-06-01", "timestamp": (timestamp + timedelta(seconds=1)).isoformat()},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"НА-3": {"p_in_mpa": 3.0, "p_out_mpa": 13.0}}
    response = client.get(
        "/objects/branches/scheme-pressures",
        params={"day": "2025-06-01", "timestamp": (timestamp + timedelta(seconds=2)).isoformat()},
    )
    assert response.status_code == 200
    assert response.json() == {}


@pytest.mark.parametrize("timestamp", ["bad", "2025-06-01T10:00:00+03:00", "2025-06-02T10:00:00"])
def test_scheme_pressure_api_validates_timestamp(branch_database, timestamp):
    response = TestClient(app).get(
        "/objects/branches/scheme-pressures", params={"day": "2025-06-01", "timestamp": timestamp}
    )
    assert response.status_code == 400


def test_scheme_pressure_api_rejects_unknown_object(branch_database):
    response = TestClient(app).get(
        "/objects/missing/scheme-pressures",
        params={"day": "2025-06-01", "timestamp": "2025-06-01T10:00:00"},
    )
    assert response.status_code == 404
