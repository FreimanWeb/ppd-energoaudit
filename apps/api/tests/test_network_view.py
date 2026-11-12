"""Разводящая сеть: сервисный слой и HTTP-контракт."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ppd_audit.config import project_root
from ppd_audit.db_seed import bootstrap_database
from ppd_audit.services import catalog, network_view
from ppd_audit.services.network_view import time_weighted_median


ROOT = project_root()
NETWORK_DIR = catalog.source_paths(ROOT)["network"]
NETWORK_CONFIG = catalog.source_paths(ROOT)["network_config"]
HAS_SOURCES = (NETWORK_DIR / "pipelines.xlsx").exists() and (
    NETWORK_DIR / "armits_wells.zip"
).exists()
needs_sources = pytest.mark.skipif(not HAS_SOURCES, reason="нет данных разводящей сети")

START = datetime(2026, 7, 1)


@pytest.fixture
def database(tmp_path):
    db = bootstrap_database(tmp_path / "audit.sqlite", ROOT / "config" / "plants")
    for hour, value in ((0, 13.9), (240, 0.2), (250, 13.9), (700, 14.0)):
        db.add_measurement("kns54an", None, START + timedelta(hours=hour), "p_bg", value, "МПа")
    return db


def test_median_carries_the_value_from_before_the_window():
    events = [(datetime(2026, 6, 30), 5.0), (datetime(2026, 7, 1, 12), 7.0)]

    assert time_weighted_median(events, START, START + timedelta(days=1)) == 5.0


def test_short_shutdown_does_not_pull_the_median_down():
    events = [(START, 10.0), (START + timedelta(hours=2), 0.0), (START + timedelta(hours=3), 10.0)]

    assert time_weighted_median(events, START, START + timedelta(days=1)) == 10.0


def test_median_of_nothing_is_none():
    assert time_weighted_median([], START, START + timedelta(days=1)) is None


def test_manifold_pressure_uses_last_month_of_telemetry(database):
    value, start, end = network_view.manifold_pressure(database, "kns54an")

    assert value == pytest.approx(13.9)
    assert end == datetime(2026, 7, 30)
    assert end - start == network_view.MANIFOLD_WINDOW


def test_station_efficiency_is_nominal_of_passports(database):
    eta = network_view.station_nominal_efficiency(database, "kns54an")

    assert 0.3 < eta < 0.9


def test_object_without_network_gets_a_clear_message(database):
    view = network_view.network_view(database, NETWORK_DIR, NETWORK_CONFIG, "kns25", tariff=5.17)

    assert "error" in view


@needs_sources
def test_view_combines_telemetry_geometry_and_cards(database):
    view = network_view.network_view(database, NETWORK_DIR, NETWORK_CONFIG, "kns54an", tariff=5.17)

    assert view["p_bg_source"]["kind"] == "telemetry"
    assert view["p_bg_mpa"] == pytest.approx(13.9)
    assert view["fluid"]["rho"] == pytest.approx(1138.0)
    assert view["eta_basis"] == "nominal"
    assert view["wells"] and view["pipelines"]
    totals = view["totals"]
    assert totals["total_kwh"] == pytest.approx(
        totals["friction_kwh"] + totals["other_kwh"] + totals["choke_kwh"]
    )
    assert totals["money_krub"] == pytest.approx(totals["total_kwh"] * 5.17 / 1000)
    assert sum(w["annual_kwh"] for w in view["wells"]) == pytest.approx(totals["total_kwh"])
    assert view["pipelines"][0]["dp_friction_mpa"] >= view["pipelines"][-1]["dp_friction_mpa"]


@needs_sources
def test_network_view_exposes_resolved_paths_for_the_schematic(database):
    view = network_view.network_view(database, NETWORK_DIR, NETWORK_CONFIG, "kns54an", tariff=5.17)
    names = {pipeline["name"] for pipeline in view["pipelines"]}
    assert any(well["path_complete"] for well in view["wells"])
    for well in view["wells"]:
        if well["q_m3h"] > 0:
            assert set(well["path_pipeline_names"]) <= names
        assert bool(well["path_pipeline_names"]) == well["has_geometry"]
    complete = next(well for well in view["wells"] if well["path_complete"])
    first = next(
        pipe for pipe in view["pipelines"] if pipe["name"] == complete["path_pipeline_names"][0]
    )
    network = network_view.plant_network(NETWORK_DIR, NETWORK_CONFIG, "kns54an")
    assert first["start"] in network.station_nodes


@needs_sources
def test_fact_efficiency_changes_only_annual_energy(database):
    nominal = network_view.network_view(
        database, NETWORK_DIR, NETWORK_CONFIG, "kns54an", tariff=5.17
    )
    fact = network_view.network_view(
        database, NETWORK_DIR, NETWORK_CONFIG, "kns54an", tariff=5.17, eta=nominal["eta"] / 2
    )

    assert fact["eta_basis"] == "fact"
    assert fact["totals"]["friction_kw"] == pytest.approx(nominal["totals"]["friction_kw"])
    assert fact["totals"]["total_kwh"] == pytest.approx(2 * nominal["totals"]["total_kwh"])


@needs_sources
def test_without_telemetry_the_card_pressure_is_used(tmp_path):
    db = bootstrap_database(tmp_path / "audit.sqlite", ROOT / "config" / "plants")

    view = network_view.network_view(db, NETWORK_DIR, NETWORK_CONFIG, "kns54an", tariff=5.17)

    assert view["p_bg_source"]["kind"] == "wells"
    assert view["p_bg_mpa"] > 0


@pytest.fixture
def client(database, monkeypatch):
    from ppd_audit.api import data_routes

    monkeypatch.setattr(data_routes, "_database", lambda: database)
    app = FastAPI()
    app.include_router(data_routes.router)
    return TestClient(app)


@needs_sources
def test_network_api_returns_the_shared_view(client):
    response = client.get("/objects/kns54an/network")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["object_id"] == "kns54an"
    assert {"well", "path_pipeline_names", "dp_friction_mpa", "dp_choke_mpa", "flags"} <= set(
        body["wells"][0]
    )


def test_network_api_rejects_impossible_efficiency(client):
    assert client.get("/objects/kns54an/network", params={"eta": 1.5}).status_code == 422


def test_network_api_reports_unknown_object(client):
    assert client.get("/objects/нет/network").status_code == 404


def test_network_api_explains_missing_sources(client):
    response = client.get("/objects/kns25/network")

    assert response.status_code == 200
    assert "error" in response.json()


@needs_sources
def test_mixed_date_network_cannot_be_a_measured_balance(database):
    view = network_view.network_view(database, NETWORK_DIR, NETWORK_CONFIG, "kns54an", tariff=5.17)
    assert view.get("status") == "scenario"
    assert view["temporal_alignment"] == "mixed_or_unknown"
    assert view["flow_months"] != [view["p_bg_source"]["start"][:7]]


@needs_sources
def test_network_without_group_binding_cannot_join_registered_circuits(database):
    database.upsert_technical_place("kns54an", "separate", "Отдельный контур")
    view = network_view.network_view(database, NETWORK_DIR, NETWORK_CONFIG, "kns54an", tariff=5.17)
    assert "error" in view
    assert "totals" not in view
