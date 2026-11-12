"""Страница подробностей статьи карты потерь (клик по столбцу)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ppd_audit.core.audit import audit_aggregate
from ppd_audit.core.pump import KnsDecomposition
from ppd_audit.services.armits_data import load_network
from ppd_audit.services.diagnostics import diagnose_aggregate
from ppd_audit.services.loss_article_details import build_loss_detail, loss_key
from ppd_audit.services.network_losses import build_network_analysis
from ppd_audit.services.pump_recommendations import recommendations
from ppd_audit.services.result_scope import result_scope
from ppd_audit.spec import load_object_spec


@pytest.fixture(scope="module")
def audit():
    spec = load_object_spec("kns54an")
    return audit_aggregate(next(item for item in spec.aggregates if item.id == "НА-1"))


@pytest.fixture(scope="module")
def network(audit):
    return build_network_analysis(audit, load_network("kns54an"))


def _detail(key, audit, network=None):
    return build_loss_detail(
        key,
        audit,
        tariff=5.17,
        t_year=8000,
        network=network,
        recs=recommendations(
            audit,
            "kns54an",
            "НА-1",
            diagnose_aggregate("kns54an", audit, result_scope(audit), None),
        ),
    )


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Номинальные потери НА", "nominal"),
        ("Потери на участке Насос–БГ", "pump_bg"),
        ("Потери в трубопроводах", "pipes"),
        ("Штуцирование нагнетательных скважин", "choke"),
        ("Потери КПД", "efficiency"),
    ],
)
def test_bar_names_resolve_to_detail_keys(name, key):
    assert loss_key(name) == key


def test_nominal_loss_splits_into_equipment_at_passport_efficiency(audit):
    detail = _detail("nominal", audit)

    assert isinstance(audit.decomposition, KnsDecomposition)
    assert detail["power_kw"] == pytest.approx(audit.decomposition.dp_nominal)
    parts = sum(row["power_kw"] for row in detail["components"]["rows"])
    assert parts == pytest.approx(detail["power_kw"], rel=1e-6)
    assert detail["annual_money_krub"] == pytest.approx(detail["power_kw"] * 8000 * 5.17 / 1000)


def test_throttle_detail_uses_methodology_annual_energy_and_checks(audit):
    detail = _detail("pump_bg", audit)

    assert detail["annual_kwh"] == pytest.approx(audit.dw_throttle)
    rows = {row["name"][:20]: row["power_kw"] for row in detail["components"]["rows"]}
    assert sum(rows.values()) == pytest.approx(audit.decomposition.dp_throttle)
    assert {check["id"] for check in detail["checks"]} == {
        "pressure_drop_high",
        "pressure_order",
        "annual_throttle_loss",
    }


def test_pipeline_detail_lists_pipelines_by_friction(audit, network):
    detail = _detail("friction", audit, network)
    rows = detail["components"]["rows"]

    assert rows and rows[0]["power_kw"] >= rows[-1]["power_kw"]
    assert all(row["roughness_mm"] in {0.01, 0.02, 0.5} for row in rows)
    assert detail["stage"] == "pipes"


def test_choke_detail_lists_every_well(audit, network):
    detail = _detail("choke", audit, network)

    assert len(detail["components"]["rows"]) == len(network["wells"])
    assert detail["stage"] == "wells"


def test_power_totals_have_no_detail(audit):
    with pytest.raises(ValueError):
        _detail("bg", audit)


def test_loss_detail_api(monkeypatch):
    from ppd_audit.api import analysis_routes

    app = FastAPI()
    app.include_router(analysis_routes.router)
    client = TestClient(app)
    response = client.post(
        "/objects/kns54an/aggregates/НА-1/loss-article-detail",
        json={"source": "field_trip", "loss": "nominal"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["key"] == "nominal" and body["power_kw"] > 0
    assert (
        client.post(
            "/objects/kns54an/aggregates/НА-1/loss-article-detail",
            json={"source": "field_trip", "loss": "useful"},
        ).status_code
        == 400
    )
