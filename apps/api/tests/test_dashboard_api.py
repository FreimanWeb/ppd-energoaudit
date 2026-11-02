from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from ppd_audit.api.main import app
from ppd_audit.db import AuditDatabase


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("fixture", "Тестовая КНС", "НГДУ", "пресная", "кнс")
    db.upsert_aggregate("fixture", "НА-02", "работа")
    db.add_passport(
        "fixture",
        "НА-02",
        valid_from=datetime(2020, 1, 1),
        pump_model="ЦНС 40-1000",
        pump_kind="центробежный",
        pump_q_nom=40,
        pump_h_nom=1000,
        pump_eta_nom=0.52,
        motor_model="ЭД",
        motor_p_nom=400,
        motor_eta_nom=0.949,
    )
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 210, "кВт"),
        ("density", 1000, "кг/м³"),
        ("q_day", 48, "м³/сут"),
        ("runtime", 2, "ч"),
        ("energy", 420, "кВт·ч"),
    ]:
        db.add_measurement(
            "fixture", "НА-02", start, metric, value, unit, source_file="fixture.xlsx"
        )
    db.add_measurement("fixture", "НА-02", start + timedelta(hours=1), "power", 210, "кВт")
    db.add_measurement("fixture", "НА-02", start + timedelta(hours=2), "power", 0, "кВт")
    db.add_measurement("fixture", "НА-02", start + timedelta(days=1), "p_in", 1, "МПа")
    monkeypatch.setenv("PPD_DATABASE_PATH", str(db.path))
    return TestClient(app), db


def test_dashboard_selection_and_snapshot_audit(dashboard):
    client, _ = dashboard
    base = "/objects/fixture/aggregates/НА-02"
    aggregates = client.get("/objects/fixture/aggregates")
    assert aggregates.status_code == 200
    assert client.get(base + "/dates").json() == {
        "dates": ["2026-07-24", "2026-07-25"],
        "default_date": "2026-07-24",
    }
    snapshots = client.get(base + "/snapshots", params={"day": "2026-07-24"})
    assert snapshots.status_code == 200
    assert snapshots.json()[0]["power_kw"] == 210
    response = client.post(
        base + "/snapshot-audit",
        json={
            "day": "2026-07-24",
            "timestamp": snapshots.json()[0]["timestamp"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["audit"]["aggregate_id"] == "НА-02"
    assert body["quality"]["status"] == "assumptions"
    assert body["scope"]["annual_runtime_is_assumed"] is True
    assert body["scope"]["daily_kpi_is_fact"] is True
    assert body["regime"]["q_day"] == 48
    assert body["sources"]
    assert body["losses"]
    topology = client.get("/objects/fixture/topology").json()
    assert topology["is_typical"] is True
    assert any(node.get("agg") == "НА-02" for node in topology["nodes"])


def test_readiness_uses_selected_snapshot_inputs(dashboard):
    client, _ = dashboard
    base = "/objects/fixture/aggregates/НА-02"
    stamp = client.get(base + "/snapshots?day=2026-07-24").json()[0]["timestamp"]
    result = client.get(base + "/onboarding", params={"at": "2026-07-24", "timestamp": stamp})
    assert result.status_code == 200, result.text
    checks = {check["field"]: check for check in result.json()["checks"]}
    assert checks["Телеметрия: p_вх"]["value"] == 1.2
    assert checks["Телеметрия: p_вых"]["value"] == 10.4
    assert checks["Плотность ρ"]["value"] == 1000
    assert result.json()["basis"]["timestamp"] == stamp
    assert result.json()["basis"]["source"] == "telemetry"
    for invalid in ("2026-07-25T00:00:00", "2026-07-24T00:00:00+03:00", "bad"):
        assert (
            client.get(
                base + "/onboarding",
                params={
                    "at": "2026-07-24",
                    "timestamp": invalid,
                },
            ).status_code
            == 400
        )


@pytest.mark.parametrize(
    "path",
    [
        "/objects/missing/aggregates",
        "/objects/missing/topology",
        "/objects/fixture/aggregates/missing/dates",
        "/objects/fixture/aggregates/missing/snapshots?day=2026-07-24",
    ],
)
def test_unknown_dashboard_ids_are_404(dashboard, path):
    assert dashboard[0].get(path).status_code == 404


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-07-25T00:00:00",
        "2026-07-24T12:00:00",
        "2026-07-24T00:00:00+03:00",
    ],
)
def test_snapshot_rejects_wrong_day_missing_or_offset_timestamp(dashboard, timestamp):
    response = dashboard[0].post(
        "/objects/fixture/aggregates/НА-02/snapshot-audit",
        json={
            "day": "2026-07-24",
            "timestamp": timestamp,
        },
    )
    assert response.status_code == 400


def test_unfit_snapshot_has_no_loss_conclusions(dashboard):
    client, db = dashboard
    db.add_measurement("fixture", "НА-02", datetime(2026, 7, 24), "q_day", 4800, "м³/сут")
    response = client.post(
        "/objects/fixture/aggregates/НА-02/snapshot-audit",
        json={
            "day": "2026-07-24",
            "timestamp": "2026-07-24T00:00:00",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["quality"]["status"] == "unfit"
    assert response.json()["losses"] == []
    assert all(value is None for value in response.json()["annual_summary"].values())


def test_snapshot_date_max_is_a_client_error(dashboard):
    response = dashboard[0].get(
        "/objects/fixture/aggregates/НА-02/snapshots", params={"day": "9999-12-31"}
    )
    assert response.status_code == 400


@pytest.mark.parametrize("day", ["not-a-date", "2026-07-24T00:00:00", "20260724"])
def test_snapshot_rejects_invalid_day(dashboard, day):
    response = dashboard[0].get(
        "/objects/fixture/aggregates/НА-02/snapshots",
        params={"day": day},
    )
    assert response.status_code == 400


def test_snapshot_audit_unknown_aggregate_is_404(dashboard):
    response = dashboard[0].post(
        "/objects/fixture/aggregates/missing/snapshot-audit",
        json={"day": "2026-07-24", "timestamp": "2026-07-24T00:00:00"},
    )
    assert response.status_code == 404


def test_typical_scheme_connects_pumps_directly_to_manifold(dashboard):
    client, _ = dashboard
    response = client.get("/objects/fixture/topology")
    assert response.status_code == 200
    graph = response.json()
    assert all(node["label"] != "Выход из станции" for node in graph["nodes"])
    edges = {(edge["from"], edge["to"]) for edge in graph["edges"]}
    for node in graph["nodes"]:
        if node["type"] == "pump":
            assert (node["id"], "comb") in edges


def test_snapshot_economics_uses_selected_year_tariff_from_database(dashboard):
    client, db = dashboard
    db.upsert_electricity_tariff(
        date(2026, 1, 1), date(2026, 12, 31), 6.25, source="Test correction"
    )
    db.upsert_electricity_tariff(date(2027, 1, 1), date(2027, 12, 31), 9.0, source="Test next year")
    response = client.post(
        "/objects/fixture/aggregates/НА-02/snapshot-audit",
        json={"day": "2026-07-24", "timestamp": "2026-07-24T00:00:00"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["tariff"] == 6.25
    for loss in data["losses"]:
        assert loss["annual_rub"] == pytest.approx(loss["annual_kwh"] * 6.25)


def test_missing_period_uses_nearest_tariff_with_warning(dashboard):
    client, db = dashboard
    with db._connection() as connection:
        connection.execute("DELETE FROM electricity_tariffs WHERE valid_from = '2026-01-01'")
    response = client.post(
        "/objects/fixture/aggregates/НА-02/snapshot-audit",
        json={"day": "2026-07-24", "timestamp": "2026-07-24T00:00:00"},
    )
    assert response.status_code == 200
    assert response.json()["tariff"] == 4.68
    assert "ближайший тариф" in response.json()["tariff_warning"]
    assert "2025-12-31" in response.json()["tariff_warning"]


def test_aggregate_without_telemetry_or_passport_is_available(dashboard):
    client, db = dashboard
    db.upsert_aggregate("fixture", "НА-03", "резерв")
    response = client.get("/objects/fixture/aggregates")
    assert response.status_code == 200
    aggregate = next(a for a in response.json() if a["code"] == "НА-03")
    assert aggregate["role"] == "резерв"
    assert aggregate["pump_model"] is None
    assert aggregate["has_telemetry"] is False
    assert client.get("/objects/fixture/aggregates/НА-03/dates").json() == {
        "dates": [],
        "default_date": None,
    }


def test_config_topology_keeps_source_and_links_real_aggregates(dashboard):
    client, db = dashboard
    db.upsert_plant("dns7s", "ДНС-7с", "НГДУ", "пресная", "кнс")
    db.upsert_aggregate("dns7s", "Н-4", "работа")
    response = client.get("/objects/dns7s/topology")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "реконструкция по паспорту/телеметрии (НА Н-1…Н-4)"
    assert body["is_typical"] is False
    assert any(node.get("agg") == "Н-4" for node in body["nodes"])
    assert all("from" in edge and "to" in edge for edge in body["edges"])


def test_snapshot_view_retains_math_and_exposes_passport_and_annual_basis(dashboard):
    response = dashboard[0].post(
        "/objects/fixture/aggregates/НА-02/snapshot-audit",
        json={"day": "2026-07-24", "timestamp": "2026-07-24T00:00:00"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body.get("source") == "telemetry"
    assert body["passport"]["pump"]["model"] == "ЦНС 40-1000"
    assert body["passport"]["motor"]["p_nom"] == 400
    assert body["regime"]["rho"] == 1000
    assert body["audit"]["metrics"]["flow_m3h"] == pytest.approx(24)
    assert body["audit"]["metrics"]["p_hydraulic_kw"] == pytest.approx(9.2 * 24 / 3.6)
    assert body["audit"]["metrics"]["sec_fact_kwh_m3"] == pytest.approx(8.75)
    assert body["annual_summary"]["efficiency_money_krub"] == pytest.approx(
        body["audit"]["metrics"]["dw_efficiency_kwh_year"] * body["tariff"] / 1000
    )


def test_snapshot_trace_includes_shared_formula_presentation(dashboard):
    response = dashboard[0].post(
        "/objects/fixture/aggregates/НА-02/snapshot-audit",
        json={"day": "2026-07-24", "timestamp": "2026-07-24T00:00:00"},
    )
    assert response.status_code == 200
    entry = response.json()["audit"]["trace"]["8"]
    assert entry.get("latex"), "math presentation must be available to both frontends"
    assert entry.get("name") == "Фактический напор, м"
    assert entry["formula"] and entry["subst"]
