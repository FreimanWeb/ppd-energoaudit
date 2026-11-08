"""Справочные сведения к диагностике насосных агрегатов."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ppd_audit.core.audit import audit_aggregate
from ppd_audit.services import pump_recommendations as service
from ppd_audit.spec import load_object_spec


def _audit(object_id: str, aggregate_id: str):
    spec = load_object_spec(object_id)
    aggregate = next(item for item in spec.aggregates if item.id == aggregate_id)
    return audit_aggregate(aggregate)


@pytest.mark.parametrize(
    ("object_id", "aggregate_id", "item"),
    [("knsopu", "НА-3", "3.4"), ("kns54an", "НА-1", "2.5"), ("kns97pren", "НА-2 ПР", "1.8")],
)
def test_motor_benchmark_finds_the_same_series_and_power(object_id, aggregate_id, item):
    result = service.motor_benchmark(_audit(object_id, aggregate_id))

    assert result["item"] == item
    assert result["best_efficiency_pct"]


def test_pump_benchmark_class_follows_daily_flow():
    result = service.pump_benchmark(_audit("kns54an", "НА-1"))

    assert result["daily_flow_m3"] > 2000
    assert result["class"] == "свыше 2000"
    assert result["efficient_sec"] < result["current_sec"]


def test_high_head_pumps_are_outside_the_cnsn_appendix():
    result = service.pump_range(_audit("kns54an", "НА-1"))

    assert result["found"] is False
    assert result["q_min_m3h"] == pytest.approx(0.7 * 180)
    assert result["q_max_m3h"] == pytest.approx(1.2 * 180)


def test_defects_are_grouped_and_linked_to_the_algorithm():
    history = service.defect_history("kns54an", "НА-1")

    assert history["total"] == 32
    assert sum(kind["count"] for kind in history["by_kind"]) == history["total"]
    leak = next(
        kind for kind in history["by_kind"] if kind["kind"].startswith("Внешняя утечка – п")
    )
    assert [row["id"] for row in leak["algorithm"]] == [16]
    assert history["recent"][0]["date"] >= history["recent"][-1]["date"]


def test_aggregate_without_journal_has_no_history():
    assert service.defect_history("kns54an", "НА-9") is None


@pytest.fixture
def client():
    from ppd_audit.api import analysis_routes, data_routes

    app = FastAPI()
    app.include_router(analysis_routes.router)
    app.include_router(data_routes.router)
    return TestClient(app)


def test_reference_api_serves_all_materials(client):
    body = client.get("/reference").json()

    assert body["hydraulics"]["roughness"]
    rules = body["diagnostic_rules"]
    assert len(rules["rules"]) == 14 == len({rule["id"] for rule in rules["rules"]})
    assert rules["source"]["artifact_id"] == "A-2026-023"
    assert {item["object_id"] for item in rules["bindings"]} == {"kns54an", "knsopu", "kns97pren"}
    assert body["pump_benchmark"][0]["rows"]
    assert sum(len(group["items"]) for group in body["motor_benchmark"]) == 27
    assert len(body["critical_parameters"]["rows"]) == 16
    assert body["critical_parameters"]["pump_ranges"]


def test_recommendations_api_for_field_trip(client):
    response = client.post(
        "/objects/knsopu/aggregates/НА-1/recommendations", json={"source": "field_trip"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pump_model"].startswith("ЦНС 63")
    # Правила считает адресная диагностика; рабочая область без сверки с паспортом
    # не даёт вывода о подаче.
    rules = {rule["id"]: rule for rule in body["diagnostics"]["rules"]}
    assert len(rules) == 14
    assert rules["flow_high"]["status"] == "pending_confirmation"
    assert body["values"]["q_nom_m3h"] == pytest.approx(63.0)
    assert body["defects"]["total"] > 0
    assert body["quality"]["status"]
