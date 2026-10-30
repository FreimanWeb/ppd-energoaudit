"""Monitoring keeps daily balances separate from synchronous measurements."""

from datetime import UTC, date, datetime
from importlib import import_module, util

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ppd_audit.db import AuditDatabase


@pytest.fixture
def database(tmp_path):
    db = AuditDatabase(tmp_path / "monitoring.sqlite")
    db.migrate()
    db.upsert_plant("test", "КНС тест", "НГДУ", "пресная", "кнс")
    db.upsert_plant("empty", "Нет данных", "НГДУ", "пресная", "кнс")
    db.upsert_aggregate("test", "A", "работа")
    db.upsert_aggregate("test", "B", "работа")
    return db


def monitoring():
    assert util.find_spec("ppd_audit.services.monitoring") is not None, "monitoring service missing"
    return import_module("ppd_audit.services.monitoring")


def add(db, aggregate, timestamp, **metrics):
    units = {
        "q_day": "м³/сут",
        "energy": "кВт·ч",
        "runtime": "ч",
        "flow_rate": "м³/ч",
        "power": "кВт",
        "p_in": "МПа",
        "p_out": "МПа",
    }
    for metric, value in metrics.items():
        db.add_measurement(
            "test", aggregate, datetime.fromisoformat(timestamp), metric, value, units[metric]
        )


def test_daily_history_is_not_upsampled_or_mixed_with_instantaneous_pressure(database):
    add(database, "A", "2026-07-01T00:00:00", q_day=100, energy=200, runtime=10)
    add(database, "A", "2026-07-01T02:00:00", p_in=1, p_out=10)
    result = monitoring().object_timeline(database, "test", "A", date(2026, 7, 1), date(2026, 7, 1))
    daily = [p for p in result["points"] if p["sec_kwh_m3"] is not None]
    assert len(daily) == 1
    assert daily[0]["sec_kwh_m3"] == 2
    assert daily[0]["efficiency"] is None
    assert daily[0]["flow_m3h"] is None
    assert daily[0]["power_kw"] is None
    assert result["basis"] == "daily"


def test_station_sec_is_ratio_of_matching_sums_not_mean(database):
    add(database, "A", "2026-07-01T00:00:00", q_day=100, energy=100)
    add(database, "B", "2026-07-01T00:00:00", q_day=300, energy=900)
    result = monitoring().object_timeline(
        database, "test", None, date(2026, 7, 1), date(2026, 7, 1)
    )
    assert result["points"][0]["sec_kwh_m3"] == 2.5
    assert result["points"][0]["efficiency"] is None


def test_station_volume_never_pairs_with_partial_aggregate_energy(database):
    add(database, None, "2026-07-01T00:00:00", q_day=1000)
    add(database, "A", "2026-07-01T00:00:00", energy=300)
    result = monitoring().object_timeline(
        database, "test", None, date(2026, 7, 1), date(2026, 7, 1)
    )
    assert result["points"][0]["sec_kwh_m3"] is None
    assert result["points"][0]["volume_m3"] == 1000


def test_synchronous_interval_metrics_and_gaps(database):
    for hour in (0, 4):
        add(
            database,
            "A",
            f"2026-07-01T{hour:02}:00:00",
            flow_rate=100,
            power=200,
            p_in=1,
            p_out=4.6,
        )
    result = monitoring().object_timeline(database, "test", "A", date(2026, 7, 1), date(2026, 7, 1))
    assert result["basis"] == "interval"
    points = {p["timestamp"]: p for p in result["points"]}
    assert points["2026-07-01T00:00:00"]["sec_kwh_m3"] == 2
    assert points["2026-07-01T00:00:00"]["efficiency"] == pytest.approx(0.5)
    assert points["2026-07-01T02:00:00"]["quality"] == "missing"
    assert points["2026-07-01T02:00:00"]["flow_m3h"] is None
    assert points["2026-07-01T02:00:00"]["snapshot_timestamp"] is None


def test_portfolio_separates_stale_and_attention_and_keeps_empty_objects(database):
    add(database, "A", "2026-07-01T00:00:00", q_day=100, energy=100)
    add(database, "A", "2026-07-02T00:00:00", q_day=100, energy=120)
    result = monitoring().monitoring_objects(database, now=datetime(2026, 10, 15, tzinfo=UTC))
    objects = {item["code"]: item for item in result["objects"]}
    assert objects["test"]["data_status"] == "stale"
    assert objects["test"]["status"] == "unknown"
    assert objects["test"]["comparison_status"] == "attention"
    assert objects["test"]["change_pct"] == pytest.approx(20)
    assert objects["empty"]["status"] == "unknown"
    assert objects["empty"]["data_status"] == "missing"


def test_portfolio_stale_normal_history_is_not_a_current_normal_state(database):
    add(database, "A", "2026-07-01T00:00:00", q_day=100, energy=100)
    add(database, "A", "2026-07-02T00:00:00", q_day=100, energy=105)
    item = next(
        o
        for o in monitoring().monitoring_objects(database, now=datetime(2026, 10, 15, tzinfo=UTC))[
            "objects"
        ]
        if o["code"] == "test"
    )
    assert item["status"] == "unknown"
    assert item["comparison_status"] == "normal"
    assert item["change_pct"] == pytest.approx(5)


def test_portfolio_fresh_pressure_does_not_make_old_kpi_current(database):
    add(database, "A", "2026-10-10T00:00:00", flow_rate=100, power=200)
    add(database, "A", "2026-10-10T02:00:00", flow_rate=100, power=201)
    add(database, "A", "2026-10-15T10:00:00", p_in=1)
    item = next(
        o
        for o in monitoring().monitoring_objects(
            database, now=datetime(2026, 10, 15, 8, tzinfo=UTC)
        )["objects"]
        if o["code"] == "test"
    )
    assert item["data_status"] == "fresh"
    assert item["status"] == "unknown"
    assert item["comparison_status"] == "normal"


def test_portfolio_fresh_signal_only_compares_last_two_points(database):
    for hour, power in ((0, 100), (2, 109), (4, 118)):
        add(database, "A", f"2026-10-15T{hour:02}:00:00", flow_rate=100, power=power)
    item = next(
        o
        for o in monitoring().monitoring_objects(
            database, now=datetime(2026, 10, 15, 2, tzinfo=UTC)
        )["objects"]
        if o["code"] == "test"
    )
    assert item["status"] == "normal"
    assert item["comparison_status"] == "normal"
    assert item["change_pct"] == pytest.approx((118 / 109 - 1) * 100)


def test_portfolio_api_can_load_six_months_of_history(database, monkeypatch):
    for stamp in ("2026-01-01T00:00:00", "2026-02-01T00:00:00", "2026-07-01T00:00:00"):
        add(database, "A", stamp, q_day=100, energy=200)
    routes = import_module("ppd_audit.api.monitoring_routes")
    monkeypatch.setenv("PPD_DATABASE_PATH", str(database.path))
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)

    def measured_days(response):
        item = next(item for item in response.json()["objects"] if item["code"] == "test")
        return {point["timestamp"][:10] for point in item["history"] if point["value"] is not None}

    assert measured_days(client.get("/monitoring/objects")) == {"2026-07-01"}
    assert measured_days(client.get("/monitoring/objects?history_days=180")) == {
        "2026-02-01",
        "2026-07-01",
    }
    assert client.get("/monitoring/objects?history_days=181").status_code == 422
    assert client.get("/monitoring/objects?history_days=0").status_code == 422


def test_portfolio_history_ends_at_selected_date_without_changing_latest_reading(
    database, monkeypatch
):
    add(database, "A", "2025-01-01T00:00:00", q_day=100, energy=100)
    add(database, "A", "2026-07-01T00:00:00", q_day=100, energy=200)
    routes = import_module("ppd_audit.api.monitoring_routes")
    monkeypatch.setenv("PPD_DATABASE_PATH", str(database.path))
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    response = client.get("/monitoring/objects?history_days=7&history_end=2025-01-03")
    assert response.status_code == 200
    item = next(item for item in response.json()["objects"] if item["code"] == "test")
    assert item["history"][0]["timestamp"][:10] == "2024-12-28"
    assert item["history"][-1]["timestamp"][:10] == "2025-01-03"
    assert [p["value"] for p in item["history"] if p["value"] is not None] == [1]
    assert item["latest_at"] == "2026-07-01T00:00:00"
    assert item["sec_kwh_m3"] == 2
    assert client.get("/monitoring/objects?history_end=bad").status_code == 422
    assert client.get("/monitoring/objects?history_end=9999-12-31").status_code == 400


def test_portfolio_summary_does_not_load_or_build_history(database, monkeypatch):
    add(database, "A", "2026-07-01T00:00:00", q_day=100, energy=200)
    routes = import_module("ppd_audit.api.monitoring_routes")
    service = monitoring()
    monkeypatch.setenv("PPD_DATABASE_PATH", str(database.path))
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    full = client.get("/monitoring/objects").json()

    def no_history(*args, **kwargs):
        pytest.fail("summary must not build history")

    monkeypatch.setattr(service, "_gap_points", no_history)
    summary = client.get("/monitoring/objects?include_history=false")
    assert summary.status_code == 200
    for item, expected in zip(summary.json()["objects"], full["objects"], strict=True):
        assert item == {**expected, "history": []}


def test_separate_portfolio_history_matches_combined_response(database, monkeypatch):
    add(database, "A", "2025-01-01T00:00:00", q_day=100, energy=100)
    add(database, "A", "2026-07-01T00:00:00", q_day=100, energy=200)
    routes = import_module("ppd_audit.api.monitoring_routes")
    monkeypatch.setenv("PPD_DATABASE_PATH", str(database.path))
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    params = "history_days=7&history_end=2025-01-03"
    full = client.get("/monitoring/objects?" + params).json()
    response = client.get("/monitoring/history?" + params)
    assert response.status_code == 200
    assert {item["code"]: item["history"] for item in response.json()["objects"]} == {
        item["code"]: item["history"] for item in full["objects"]
    }
    assert (
        client.get("/monitoring/history?history_days=181&history_end=2025-01-03").status_code == 422
    )
    assert client.get("/monitoring/history?history_end=9999-12-31").status_code == 400
    assert client.get("/monitoring/history?history_end=bad").status_code == 422


def test_latest_partial_reading_does_not_show_old_efficiency_as_current(database):
    add(database, "A", "2026-07-01T00:00:00", q_day=100, energy=100)
    add(database, "A", "2026-07-02T00:00:00", p_in=1)
    result = monitoring().monitoring_objects(database)
    item = next(item for item in result["objects"] if item["code"] == "test")
    assert item["latest_at"] == "2026-07-02T00:00:00"
    assert item["sec_kwh_m3"] == 1
    assert item["kpi_at"] == "2026-07-01T00:00:00"
    assert item["status"] == "unknown"


@pytest.mark.parametrize("history_end", [None, date(2026, 7, 3)])
def test_portfolio_skips_non_kpi_points_without_losing_freshness(
    database, monkeypatch, history_end
):
    add(database, "A", "2026-07-01T00:00:00", p_in=1)
    add(database, "A", "2026-07-02T00:00:00", q_day=100, energy=200)
    add(database, "A", "2026-07-03T00:00:00", power=300, p_out=10)
    service = monitoring()
    original = service._totals
    calls = []

    def totals(scopes, left, right):
        calls.append((left, right))
        return original(scopes, left, right)

    monkeypatch.setattr(service, "_totals", totals)
    result = service.monitoring_objects(database, history_end=history_end)
    item = next(item for item in result["objects"] if item["code"] == "test")
    assert item["latest_at"] == "2026-07-03T00:00:00"
    assert item["kpi_at"] == "2026-07-02T00:00:00"
    assert item["sec_kwh_m3"] == 2
    assert any(point["timestamp"] == "2026-07-01T00:00:00" for point in item["history"])
    assert all(pair == ("energy", "q_day") for pair in calls)


def test_zero_or_nonfinite_values_never_produce_infinity(database):
    add(database, "A", "2026-07-01T00:00:00", flow_rate=0, power=float("inf"), p_out=10)
    result = monitoring().object_timeline(database, "test", "A", date(2026, 7, 1), date(2026, 7, 1))
    assert result["points"][0]["sec_kwh_m3"] is None
    assert result["points"][0]["power_kw"] is None
    assert result["points"][0]["flow_m3h"] == 0


def test_monitoring_routes_validate_period_and_ids_without_bootstrap(database, monkeypatch):
    assert util.find_spec("ppd_audit.api.monitoring_routes") is not None, (
        "monitoring routes missing"
    )
    routes = import_module("ppd_audit.api.monitoring_routes")
    monkeypatch.setenv("PPD_DATABASE_PATH", str(database.path))
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    assert client.get("/monitoring/objects").status_code == 200
    assert client.get("/objects/test/timeline").status_code == 200
    assert client.get("/objects/absent/timeline").status_code == 404
    assert client.get("/objects/test/timeline?aggregate_id=absent").status_code == 404
    assert client.get("/objects/test/timeline?start=2026-02-01&end=2026-01-01").status_code == 400
    assert client.get("/objects/test/timeline?start=bad").status_code == 400
    assert client.get("/objects/test/timeline?start=2020-01-01&end=2026-01-01").status_code == 400
    missing = database.path.parent / "absent.sqlite"
    monkeypatch.setenv("PPD_DATABASE_PATH", str(missing))
    assert client.get("/monitoring/objects").status_code == 503
    assert not missing.exists()


def test_portfolio_uses_last_sec_with_its_own_timestamp(database):
    add(database, "A", "2026-07-01T00:00:00", q_day=100, energy=100)
    add(database, "A", "2026-07-01T02:00:00", power=200)
    item = next(
        o for o in monitoring().monitoring_objects(database)["objects"] if o["code"] == "test"
    )
    assert item["sec_kwh_m3"] == 1
    assert item["kpi_at"] == "2026-07-01T00:00:00"
    assert item["latest_at"] == "2026-07-01T02:00:00"
    assert item["history"][-1]["timestamp"] == "2026-07-01T00:00:00"


def test_old_aggregate_defaults_to_its_own_latest_day(database):
    add(database, "A", "2026-01-01T00:00:00", q_day=100, energy=100)
    add(database, "B", "2026-07-01T00:00:00", q_day=100, energy=100)
    result = monitoring().object_timeline(database, "test", "A")
    assert result["end"] == "2026-01-01"
    assert result["latest_at"] == "2026-01-01T00:00:00"


def test_station_pressure_does_not_invalidate_matched_aggregate_sec(database):
    add(database, None, "2026-07-01T00:00:00", p_in=0, p_out=4)
    add(database, "A", "2026-07-01T00:00:00", flow_rate=100, power=200)
    result = monitoring().object_timeline(
        database, "test", None, date(2026, 7, 1), date(2026, 7, 1)
    )
    assert result["points"][0]["sec_kwh_m3"] == 2
    assert result["points"][0]["p_in_mpa"] == 0


def test_no_unverified_snapshot_links(database):
    add(database, "A", "2026-07-01T00:00:00", q_day=100, energy=100)
    result = monitoring().object_timeline(database, "test", "A", date(2026, 7, 1), date(2026, 7, 1))
    assert result["points"][0]["snapshot_timestamp"] is None


def test_zero_reference_sec_does_not_crash_comparison(database):
    add(database, "A", "2026-07-01T00:00:00", flow_rate=100, power=0)
    add(database, "A", "2026-07-01T02:00:00", flow_rate=100, power=200)
    item = next(
        o for o in monitoring().monitoring_objects(database)["objects"] if o["code"] == "test"
    )
    assert item["change_pct"] is None


def test_selected_aggregate_snapshot_link_is_verified(database):
    add(database, "A", "2026-07-01T00:00:00", q_day=100, energy=100)
    add(database, "A", "2026-07-01T02:00:00", p_in=1, p_out=4, power=200)
    result = monitoring().object_timeline(database, "test", "A", date(2026, 7, 1), date(2026, 7, 1))
    from ppd_audit.services.telemetry_audit import telemetry_snapshots

    valid = {
        candidate.timestamp.isoformat()
        for candidate in telemetry_snapshots(
            database, "test", "A", datetime(2026, 7, 1), datetime(2026, 7, 2)
        )
    }
    assert result["points"][0]["snapshot_timestamp"] in valid


def test_naive_measurement_freshness_uses_moscow_source_time(database):
    add(database, "A", "2026-10-15T10:00:00", flow_rate=100, power=200)
    # 11:01 UTC = 14:01 Moscow, so the 10:00 local sample is older than four hours.
    result = monitoring().monitoring_objects(
        database, now=datetime(2026, 10, 15, 11, 1, tzinfo=UTC)
    )
    item = next(o for o in result["objects"] if o["code"] == "test")
    assert item["data_status"] == "stale"


def test_station_sec_rejects_one_pump_positive_flow_with_zero_energy(database):
    add(database, "A", "2026-07-01T00:00:00", q_day=100, energy=100)
    add(database, "B", "2026-07-01T00:00:00", q_day=100, energy=0)
    result = monitoring().object_timeline(
        database, "test", None, date(2026, 7, 1), date(2026, 7, 1)
    )
    assert result["points"][0]["sec_kwh_m3"] is None


@pytest.mark.parametrize(("hour_shift", "minute"), [(0, 30), (1, 0)])
def test_interval_gaps_follow_observed_phase_not_midnight_or_daily_points(
    database, hour_shift, minute
):
    add(database, "A", "2026-07-01T00:00:00", q_day=100, energy=100)
    for hour in (0, 2, 6):
        add(
            database,
            "A",
            f"2026-07-01T{hour + hour_shift:02}:{minute:02}:00",
            flow_rate=100,
            power=200,
        )
    result = monitoring().object_timeline(database, "test", "A", date(2026, 7, 1), date(2026, 7, 1))
    points = {point["timestamp"]: point for point in result["points"]}
    assert points[f"2026-07-01T{4 + hour_shift:02}:{minute:02}:00"]["quality"] == "missing"
    assert "2026-07-01T02:00:00" not in points
    assert "2026-07-01T04:00:00" not in points
    assert points["2026-07-01T00:00:00"]["basis"] == "daily"
