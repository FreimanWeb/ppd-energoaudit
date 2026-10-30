from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ppd_audit.db import AuditDatabase
from ppd_audit.services.demo import seed_demo


@pytest.fixture
def station_client(tmp_path, monkeypatch):
    from ppd_audit.api import station_routes

    database = AuditDatabase(tmp_path / "station.sqlite")
    database.migrate()
    seed_demo(database, datetime(2026, 10, 18, 12))
    monkeypatch.setattr(station_routes, "_database", lambda: database)
    app = FastAPI()
    app.include_router(station_routes.router)
    return TestClient(app), database


def test_both_pumps_and_common_latest_timestamp(station_client):
    client, database = station_client
    response = client.post("/objects/demo-ppd/station-summary", json={"source": "telemetry"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["complete"]
    assert data["timestamp"] == "2026-10-18T12:00:00"
    assert data["included_aggregates"] == ["НА-1", "НА-2"]
    assert data["aggregate_count"] == 2
    rows = [r for r in database.measurements("demo-ppd") if r["timestamp"] == data["timestamp"]]
    power = sum(r["value"] for r in rows if r["metric"] == "power")
    flow = sum(r["value"] for r in rows if r["metric"] == "flow_rate")
    assert data["metrics"]["power_kw"] == pytest.approx(power)
    assert data["metrics"]["flow_m3h"] == pytest.approx(flow)
    assert data["metrics"]["sec_kwh_m3"] == pytest.approx(power / flow)
    assert data["annual"]["efficiency_energy_kwh"] > 0
    assert data["measures"]
    assert {row["aggregate_id"] for row in data["measures"]} == {"НА-1", "НА-2"}
    assert all(row["energy_saving_kwh"] > 0 for row in data["measures"])
    assert "8760" in data["annual_basis"]
    assert "не фактические" in data["annual_basis"]
    assert data["network"]["status"] == "scenario"
    assert data["pressures"] == {
        code: {"p_in_mpa": 0.5, "p_out_mpa": 10.5} for code in ("НА-1", "НА-2")
    }


@pytest.mark.parametrize("source", ["telemetry", "field_trip"])
def test_priority_candidates_match_detail_at_common_time(station_client, monkeypatch, source):
    from ppd_audit.api import analysis_routes

    client, database = station_client
    monkeypatch.setattr(analysis_routes, "_database", lambda: database)
    client.app.include_router(analysis_routes.router)
    summary = client.post("/objects/demo-ppd/station-summary", json={"source": source}).json()
    for aggregate in summary["included_aggregates"]:
        response = client.post(
            f"/objects/demo-ppd/aggregates/{aggregate}/measures",
            json={
                "source": source,
                **(
                    {
                        "day": summary["timestamp"][:10],
                        "timestamp": summary["timestamp"],
                    }
                    if source == "telemetry"
                    else {}
                ),
            },
        )
        assert response.status_code == 200, response.text
        details = {row["measure_id"]: row for row in response.json()["annual"]}
        for candidate in summary["measures"]:
            if candidate["aggregate_id"] == aggregate:
                detail = details[candidate["measure_id"]]
                assert candidate["energy_saving_kwh"] == pytest.approx(detail["energy_saving_kwh"])
                assert candidate["money_saving_krub"] == pytest.approx(detail["money_saving_krub"])


def test_does_not_replace_explicit_missing_timestamp(station_client):
    client, database = station_client
    with database._connection() as connection:
        connection.execute(
            """DELETE FROM telemetry_measurements WHERE timestamp = ?
            AND aggregate_id IN (SELECT id FROM aggregates WHERE code = 'НА-2')""",
            ("2026-10-17T12:00:00",),
        )
    data = client.post(
        "/objects/demo-ppd/station-summary",
        json={
            "source": "telemetry",
            "day": "2026-10-17",
            "timestamp": "2026-10-17T12:00:00",
        },
    ).json()
    assert not data["complete"]
    assert all(v is None for v in data["metrics"].values())
    assert data["annual"] is None
    assert data["measures"] == []
    assert any("НА-2" in w for w in data["warnings"])


def test_field_trip_all_pumps(station_client):
    client, _ = station_client
    data = client.post("/objects/demo-ppd/station-summary", json={"source": "field_trip"}).json()
    assert data["complete"]
    assert data["aggregate_count"] == 2
    assert data["metrics"]["power_kw"] > 0
    assert data["timestamp"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"day": "2026-10-17", "timestamp": "2026-10-18T12:00:00"},
        {"day": "2026-10-17", "timestamp": "2026-10-17T12:00:00+03:00"},
    ],
)
def test_invalid_context(station_client, payload):
    client, _ = station_client
    assert client.post("/objects/demo-ppd/station-summary", json=payload).status_code == 400


def test_zero_power_does_not_crash_or_publish_partial_sum(station_client):
    client, database = station_client
    with database._connection() as connection:
        connection.execute("""UPDATE telemetry_measurements SET value = 0
            WHERE timestamp = '2026-10-18T12:00:00' AND metric = 'power'
            AND aggregate_id IN (SELECT id FROM aggregates WHERE code = 'НА-2')""")
    response = client.post("/objects/demo-ppd/station-summary", json={"source": "telemetry"})
    assert response.status_code == 200
    data = response.json()
    assert not data["complete"]
    assert all(value is None for value in data["metrics"].values())
    assert data["annual"] is None


def test_field_trip_annual_totals_are_sums_not_mean_efficiency(station_client):
    from ppd_audit.services.analysis import annual_summary
    from ppd_audit.services.catalog import get_field_trip_audit, tariff

    client, database = station_client
    data = client.post("/objects/demo-ppd/station-summary", json={"source": "field_trip"}).json()
    parts = [
        annual_summary(
            get_field_trip_audit("demo-ppd", code, database=database)[1],
            tariff(database=database)["rub_per_kwh"],
        )
        for code in ("НА-1", "НА-2")
    ]
    assert data["annual"]
    for key, value in data["annual"].items():
        assert value == pytest.approx(sum(row[key] for row in parts))


def test_mixed_assumed_and_measured_annual_runtime_not_summed(station_client, monkeypatch):
    client, database = station_client
    monkeypatch.setattr(
        database, "annual_runtime", lambda plant, code, end: 1000 if code == "НА-1" else None
    )
    data = client.post("/objects/demo-ppd/station-summary", json={"source": "telemetry"}).json()
    assert data["complete"]
    assert data["annual"] is None
    assert data["annual_basis"] is None


def test_no_common_timestamp_has_no_station_totals(station_client):
    client, database = station_client
    with database._connection() as connection:
        connection.execute("""DELETE FROM telemetry_measurements
            WHERE aggregate_id IN (SELECT id FROM aggregates WHERE code = 'НА-2')""")
    data = client.post("/objects/demo-ppd/station-summary", json={"source": "telemetry"}).json()
    assert not data["complete"]
    assert data["timestamp"] is None
    assert all(v is None for v in data["metrics"].values())
    assert data["network"]["status"] == "unavailable"


def test_field_trip_missing_runtime_is_explicit_8760_scenario(station_client, monkeypatch):
    from ppd_audit.services import station_summary
    from ppd_audit.spec import load_object_spec

    client, _ = station_client
    obj = load_object_spec("demo-ppd").model_copy(deep=True)
    for aggregate in obj.aggregates:
        aggregate.regime.t_year = None
    monkeypatch.setattr(station_summary, "load_object_spec", lambda _: obj)
    response = client.post("/objects/demo-ppd/station-summary", json={"source": "field_trip"})
    assert response.status_code == 200
    data = response.json()
    assert data["complete"]
    assert "8760" in data["annual_basis"]
    assert data["annual"]["efficiency_energy_kwh"] > 0
    assert data["measures"] == []


@pytest.mark.parametrize("case", ["bad", "bad_duplicate", "nonfinite", "conflicting"])
def test_raw_invalid_quality_cannot_override_snapshot_audit(station_client, monkeypatch, case):
    client, database = station_client
    measurements = database.measurements

    def corrupted_rows(object_id, code=None, **kwargs):
        rows = measurements(object_id, code, **kwargs)
        if code != "НА-2":
            return rows
        rows = [dict(row) for row in rows]
        target = next(
            row
            for row in rows
            if row["timestamp"] == "2026-10-18T12:00:00" and row["metric"] == "flow_rate"
        )
        if case == "bad":
            target["quality"] = "bad"
        elif case == "bad_duplicate":
            rows.append({**target, "quality": "bad"})
        elif case == "nonfinite":
            target["value"] = float("inf")
        else:
            rows.append({**target, "value": target["value"] + 1})
        return rows

    monkeypatch.setattr(database, "measurements", corrupted_rows)
    data = client.post(
        "/objects/demo-ppd/station-summary",
        json={
            "source": "telemetry",
            "day": "2026-10-18",
            "timestamp": "2026-10-18T12:00:00",
        },
    ).json()
    assert not data["complete"]
    assert all(value is None for value in data["metrics"].values())
    assert data["annual"] is None
    assert data["network"]["status"] == "unavailable"
