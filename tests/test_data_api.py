"""HTTP contracts data-слоя с локальными telemetry/CSV fixtures."""

from importlib import import_module, util

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_data_services import data_source as data_source_fixture


data_source = data_source_fixture


@pytest.fixture
def client(data_source, monkeypatch):
    assert util.find_spec("ppd_audit.api.data_routes") is not None, "нужны data API routes"
    routes = import_module("ppd_audit.api.data_routes")
    _, db, crm, tags = data_source
    monkeypatch.setattr(routes, "_database", lambda: db)
    monkeypatch.setattr(routes, "CRM_DIR", crm)
    monkeypatch.setattr(routes, "SCADA_TAGS", tags)
    monkeypatch.setattr(routes, "DOWNTIME_DIR", crm.parent / "downtime")
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_telemetry_api_preserves_state_carry_and_both_days(client):
    response = client.get(
        "/objects/test/telemetry",
        params={
            "aggregate_id": "НА-1",
            "start": "2026-01-01",
            "end": "2026-01-02",
        },
    )
    assert response.status_code == 200
    body = response.json()
    series = next(item for item in body["series"] if item["metric"] == "p_вх")
    assert series["unit"] == "МПа"
    assert series["points"][0] == {"timestamp": "2026-01-01T00:00:00", "value": 1}
    assert series["points"][-1] == {"timestamp": "2026-01-03T00:00:00", "value": 2}
    assert any(row["is_station"] for row in body["records"])


def test_forecast_api_uses_aggregate_priority_and_canonical_core(client):
    response = client.get(
        "/objects/test/aggregates/НА-1/forecast",
        params={
            "start": "2026-01-01",
            "end": "2026-01-03",
            "period_days": 1,
            "horizon": 2,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["value"] for item in body["history"]] == [100, 20, 102]
    assert len(body["forecast"]) == 2
    assert body["estimate"] is True
    assert body["period_days"] == 1
    insufficient = client.get(
        "/objects/test/aggregates/НА-1/forecast",
        params={
            "start": "2026-01-01",
            "end": "2026-01-03",
            "period_days": 30,
        },
    )
    assert insufficient.status_code == 400


def test_crm_api_serializes_existing_run_and_missing_run(client):
    runs = client.get("/objects/test/crm/runs")
    assert runs.status_code == 200
    assert runs.json()[0]["code"] == "daily"
    forecast = client.get("/objects/test/crm/runs/daily")
    assert forecast.status_code == 200
    assert forecast.json()["by_unit"] == {"НА-1": [["2026-01-01", 48.0]]}
    assert client.get("/objects/test/crm/runs/absent").status_code == 404
    assert client.get("/objects/test/crm/well-runs").json() == []
    assert client.get("/objects/test/well-downtime").json() == []


def test_calendar_and_clarifications(client, data_source):
    _, db, *_ = data_source
    db.upsert_clarification(
        "test", "НА-1", field="eta", provisional_value="0.5", reason="нужен паспорт"
    )
    response = client.get("/objects/test/aggregates/НА-1/calendar", params={"month": "2026-01"})
    assert response.status_code == 200
    assert response.json()["statuses"] == {
        "2026-01-02": "insufficient",
        "2026-01-03": "insufficient",
    }
    assert (
        client.get("/objects/test/clarifications", params={"aggregate_id": "НА-1"}).json()[0][
            "field"
        ]
        == "eta"
    )


@pytest.mark.parametrize(
    "path,params,status",
    [
        (
            "/objects/missing/telemetry",
            {"aggregate_id": "НА-1", "start": "2026-01-01", "end": "2026-01-02"},
            404,
        ),
        (
            "/objects/test/telemetry",
            {"aggregate_id": "missing", "start": "2026-01-01", "end": "2026-01-02"},
            404,
        ),
        (
            "/objects/test/telemetry",
            {"aggregate_id": "НА-1", "start": "2026-01-03", "end": "2026-01-01"},
            400,
        ),
        (
            "/objects/test/telemetry",
            {"aggregate_id": "НА-1", "start": "bad", "end": "2026-01-01"},
            400,
        ),
        ("/objects/test/aggregates/НА-1/calendar", {"month": "bad"}, 400),
        (
            "/objects/test/aggregates/НА-1/forecast",
            {"start": "2026-01-01", "end": "2026-01-03", "horizon": 999999},
            422,
        ),
        ("/objects/test/crm/well-runs/missing/graph", {"edge_limit": 999999}, 422),
    ],
)
def test_data_boundaries(client, path, params, status):
    assert client.get(path, params=params).status_code == status


def test_crm_fact_api_returns_existing_daily_series(client):
    response = client.get(
        "/objects/test/crm/fact",
        params={
            "aggregates": "НА-1",
            "start": "2026-01-01",
            "end": "2026-01-03",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "series": [
            {
                "aggregate": "НА-1",
                "points": [["2026-01-01", 100], ["2026-01-02", 20], ["2026-01-03", 102]],
            }
        ]
    }


def test_crm_well_report_and_graph_match_external_fixture(client, data_source):
    from ppd_audit.ingest.crm_wells import CENTRALITY_FILE, EDGES_FILE, REPORT_FILE

    _, _, crm, _ = data_source
    run = crm / "test" / "wells"
    run.mkdir()
    (run / REPORT_FILE).write_text(
        "Период,Нагн. скваж.,Закачка м3/мес базовый прогноз,"
        "Закачка м3/мес прогноз,Закачка м3/мес факт\n"
        "01.2026,100,10,20,25\n01.2026,200,20,30,35\n"
    )
    (run / EDGES_FILE).write_text("source,target,combined_strength\n100,200,0.8\n")
    (run / CENTRALITY_FILE).write_text(
        "injector,strength_sum,degree_centrality,betweenness_centrality,top_neighbor,top_neighbor_strength\n"
        "100,0.8,1,0,200,0.8\n"
    )
    runs = client.get("/objects/test/crm/well-runs").json()
    assert runs[0]["code"] == "wells"
    report = client.get("/objects/test/crm/well-runs/wells")
    assert report.status_code == 200
    assert report.json()["totals"] == [
        {"month": "2026-01-01", "base": 30, "forecast": 50, "fact": 60}
    ]
    assert report.json()["rows"][0]["deviation"] == -20
    graph = client.get("/objects/test/crm/well-runs/wells/graph")
    assert graph.status_code == 200
    assert set(graph.json()["positions"]) == {"100", "200"}
    assert graph.json()["edges"][0]["strength"] == 0.8
    assert graph.json()["centrality"][0]["top_neighbor"] == "200"
    assert client.get("/objects/test/crm/well-runs/absent").status_code == 404
    assert client.get("/objects/test/crm/well-runs/absent/graph").status_code == 404


def test_crm_parse_error_stays_visible_in_api(client, data_source):
    _, _, crm, _ = data_source
    (crm / "test" / "daily" / "forecast_by_equipment_and_total.csv").write_text("bad,data\n")
    response = client.get("/objects/test/crm/runs/daily")
    assert response.status_code == 200
    assert "нет столбца" in response.json()["error"]


def test_last_calendar_date_cannot_overflow_exclusive_window(client):
    response = client.get(
        "/objects/test/telemetry",
        params={
            "aggregate_id": "НА-1",
            "start": "9999-12-31",
            "end": "9999-12-31",
        },
    )
    assert response.status_code == 400


def test_daily_forecast_accepts_intended_three_year_horizon(client):
    response = client.get(
        "/objects/test/aggregates/НА-1/forecast",
        params={
            "start": "2026-01-01",
            "end": "2026-01-03",
            "period_days": 1,
            "horizon": 1095,
        },
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["forecast"]) == 1095


def test_crm_well_keys_match_downtime_trunk_names(client, data_source):
    from openpyxl import Workbook

    from ppd_audit.ingest.crm_wells import REPORT_FILE

    _, _, crm, _ = data_source
    run = crm / "test" / "wells"
    run.mkdir()
    (run / REPORT_FILE).write_text(
        "Период,Нагн. скваж.,Закачка м3/мес прогноз\n01.2026,3592Д/2,20\n"
    )
    directory = crm.parent / "downtime"
    directory.mkdir()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Сводка простоев"])
    sheet.append(["Скваж", "Причина_простоя", "Дата_непр_пр", "T_раб"])
    sheet.append(["3592Д", "Ремонт", None, 0])
    workbook.save(directory / "test.xlsx")
    report = client.get("/objects/test/crm/well-runs/wells").json()
    assert report["rows"][0]["well_key"] == "3592Д"
    downtime = client.get("/objects/test/well-downtime").json()
    assert downtime[0]["well_key"] == report["rows"][0]["well_key"]


def test_crm_monthly_view_filters_actual_downtime_workbook(client, data_source):
    from openpyxl import Workbook

    from ppd_audit.ingest.crm_wells import REPORT_FILE

    _, _, crm, _ = data_source
    run = crm / "test" / "wells"
    run.mkdir()
    (run / REPORT_FILE).write_text(
        "Период,Нагн. скваж.,Закачка м3/мес прогноз\n"
        "12.2025,100/2,20\n01.2026,100/2,30\n01.2026,200,40\n"
    )
    directory = crm.parent / "downtime"
    directory.mkdir()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Сводка простоев"])
    sheet.append(["Скваж", "Причина_простоя", "Дата_непр_пр", "T_раб"])
    for well, since in [
        ("100", "2025-11-30T23:59:59"),
        ("100", "2025-12-01T00:00:00"),
        ("200", "2026-01-15T00:00:00"),
        ("100", "2026-02-01T00:00:00"),
    ]:
        sheet.append([well, "Ремонт", since.replace("T", " "), 0])
    workbook.save(directory / "test.xlsx")
    response = client.get("/objects/test/crm/well-runs/wells/monthly", params={"well": "100/2"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["forecast"] for row in body["series"]] == [20, 30]
    assert body["window"] == ["2025-12-01T00:00:00", "2026-02-01T00:00:00"]
    assert body["last"] == body["series"][-1]
    assert [mark["since"] for mark in body["downtime_marks"]] == ["2025-12-01T00:00"]
    assert body["downtime_marks"][0]["well_key"] == "100"
    empty = client.get("/objects/test/crm/well-runs/wells/monthly", params={"well": "missing"})
    assert empty.json() == {"series": [], "downtime_marks": [], "window": None, "last": None}
    assert client.get("/objects/test/crm/well-runs/absent/monthly").status_code == 404
