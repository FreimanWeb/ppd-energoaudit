"""Нейтральные тесты data-слоя сервисов на локальных fixtures."""

import sys
from datetime import date, datetime

import pytest


def test_characterization_station_priority_and_inclusive_window(data_source):
    from ppd_audit.services import catalog, telemetry_view

    db, crm, tags = data_source
    assert telemetry_view.daily_injection_series(
        db, "test", "НА-1", date(2026, 1, 1), date(2026, 1, 3)
    ) == [
        ("2026-01-01", 100),
        ("2026-01-02", 20),
        ("2026-01-03", 102),
    ]
    rows = telemetry_view.telemetry_for_period(
        db, "test", "НА-1", date(2026, 1, 1), date(2026, 1, 2)
    )
    assert any(row["timestamp"] == "2025-12-31T23:00:00" for row in rows)
    assert not any(
        row["metric"] == "q_day" and row["timestamp"].startswith("2026-01-03") for row in rows
    )
    assert any(
        row["metric"] == "p_in" and row["timestamp"].startswith("2026-01-03") for row in rows
    )
    assert catalog.object_index(db)[0]["id"] == "test"


def test_topology_files_valid():
    """config/topology/*.yaml: у узлов есть x/y/label, рёбра ссылаются на существующие узлы."""
    import yaml

    from ppd_audit.config import project_root

    files = list((project_root() / "config" / "topology").glob("*.yaml"))
    assert files, "нет файлов топологии"
    for f in files:
        t = yaml.safe_load(f.read_text(encoding="utf-8"))
        ids = {n["id"] for n in t["nodes"]}
        for n in t["nodes"]:
            assert {"x", "y", "label"} <= set(n), f"{f.name}: узел без x/y/label: {n}"
        for e in t.get("edges", []):
            assert e["from"] in ids and e["to"] in ids, f"{f.name}: битое ребро {e}"


def test_characterization_crm_mapping_missing_run_and_source_error(data_source):
    from ppd_audit.services import crm_view, forecast_data

    db, crm, tags = data_source
    result = crm_view.crm_daily_forecast(crm, tags, "test", "daily")
    assert result["by_unit"] == {"НА-1": [("2026-01-01", 48.0)]}
    assert result["total"] == [("2026-01-01", 48.0)]
    assert crm_view.crm_daily_forecast(crm, tags, "test", "absent") is None
    assert crm_view.well_downtime(crm.parent / "downtime", "test") == []
    assert forecast_data.injection_profile(db, "test", "НА-1", 1000, period_days=30) is None
    (crm / "test" / "daily" / "forecast_by_equipment_and_total.csv").write_text("bad,data\n")
    assert "error" in crm_view.crm_daily_forecast(crm, tags, "test", "daily")


def test_crm_source_errors_are_returned_as_data(data_source):
    from ppd_audit.services import crm_view

    _, crm, tags = data_source
    tags.unlink()
    assert "error" in crm_view.crm_daily_forecast(crm, tags, "test", "daily")


def test_forecast_service_returns_canonical_history_and_core_results(data_source):
    from ppd_audit.services import forecast_data

    db, _, _ = data_source
    body = forecast_data.forecast_series(
        db,
        "test",
        "НА-1",
        date(2026, 1, 1),
        date(2026, 1, 3),
        period_days=1,
        horizon=2,
    )
    assert [(point["period"], point["value"]) for point in body["history"]] == [
        (-2, 100),
        (-1, 20),
        (0, 102),
    ]
    assert len(body["forecast"]) == 2
    assert [point["period"] for point in body["forecast"]] == [1, 2]
    assert max(point["period"] for point in body["history"]) < min(
        point["period"] for point in body["forecast"]
    )
    assert body["method"] == "linear-trend"
    assert body["estimate"] is True


def test_crm_graph_includes_existing_spring_layout(data_source):
    from ppd_audit.ingest.crm_wells import EDGES_FILE, REPORT_FILE
    from ppd_audit.services import crm_view

    _, crm, _ = data_source
    run = crm / "test" / "wells"
    run.mkdir()
    (run / REPORT_FILE).write_text(
        "Период,Нагн. скваж.,Закачка м3/мес прогноз\n01.2026,100,20\n01.2026,200,30\n"
    )
    (run / EDGES_FILE).write_text("source,target,combined_strength\n100,200,0.8\n")
    graph = crm_view.crm_wells_graph(crm, "test", "wells")
    assert "positions" in graph
    assert set(graph["positions"]) == {"100", "200"}
    assert graph["edges"] == [{"source": "100", "target": "200", "strength": 0.8}]
    assert all(len(point) == 2 for point in graph["positions"].values())


def test_source_paths_honor_optional_environment_overrides(tmp_path, monkeypatch):
    from ppd_audit.services import catalog

    monkeypatch.setenv("PPD_CRM_DIR", str(tmp_path / "custom-crm"))
    monkeypatch.setenv("PPD_DOWNTIME_DIR", str(tmp_path / "custom-downtime"))
    monkeypatch.setenv("PPD_SCADA_TAGS_PATH", str(tmp_path / "custom.yaml"))
    monkeypatch.setenv("PPD_NETWORK_DIR", str(tmp_path / "custom-network"))
    monkeypatch.setenv("PPD_NETWORK_CONFIG", str(tmp_path / "network.yaml"))
    paths = catalog.source_paths(tmp_path)
    assert paths == {
        "crm": tmp_path / "custom-crm",
        "downtime": tmp_path / "custom-downtime",
        "scada_tags": tmp_path / "custom.yaml",
        "network": tmp_path / "custom-network",
        "network_config": tmp_path / "network.yaml",
    }


def test_neutral_data_services_import_when_ui_packages_are_blocked():
    import subprocess

    script = """
import sys
from importlib.abc import MetaPathFinder
class BlockUi(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'streamlit', 'plotly'}:
            raise AssertionError('UI dependency: ' + fullname)
sys.meta_path.insert(0, BlockUi())
from ppd_audit.services import catalog, telemetry_view, crm_view, forecast_data
assert all(module.__file__ for module in (catalog, telemetry_view, crm_view, forecast_data))
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "end,period_days,daily_count,period_count",
    [
        (date(2026, 1, 2), 1, 2, 2),
        (date(2026, 1, 3), 30, 3, 0),
    ],
)
def test_forecast_reports_insufficient_counts(
    data_source,
    end,
    period_days,
    daily_count,
    period_count,
):
    from ppd_audit.services import forecast_data

    database, *_ = data_source
    with pytest.raises(forecast_data.InsufficientForecastData) as error:
        forecast_data.forecast_series(
            database,
            "test",
            "НА-1",
            date(2026, 1, 1),
            end,
            period_days=period_days,
        )
    assert error.value.daily_count == daily_count
    assert error.value.period_count == period_count
    assert isinstance(error.value, ValueError)


@pytest.fixture
def monthly_report():
    return {
        "totals": [
            {"month": "2025-12-01", "base": 50, "forecast": 60, "fact": None},
            {"month": "2026-01-01", "base": 70, "forecast": 80, "fact": 90},
        ],
        "rows": [
            {"month": "2025-12-01", "well": "100", "base": None, "forecast": None, "fact": None},
            {"month": "2026-01-01", "well": "100", "base": 20, "forecast": 30, "fact": 40},
            {"month": "2026-01-01", "well": "200", "base": 50, "forecast": 50, "fact": 50},
        ],
    }


@pytest.fixture
def downtime_records():
    return [
        {"well": str(index), "reason": "Ремонт", "since": since}
        for index, since in enumerate([
            "2025-11-30T23:59:59",
            "2025-12-01T00:00:00",
            "2026-01-31T23:59:59",
            "2026-02-01T00:00:00",
            None,
        ])
    ]


def test_characterization_crm_observed_station_summation(data_source):
    from ppd_audit.services import crm_view, telemetry_view

    db, *_ = data_source
    db.upsert_aggregate("test", "НА-2", "работа")
    db.add_measurement("test", "НА-2", datetime(2026, 1, 1), "q_day", 5, "м³/сут")
    series = [
        telemetry_view.daily_injection_series(
            db, "test", aggregate, date(2026, 1, 1), date(2026, 1, 3)
        )
        for aggregate in ("НА-1", "НА-2")
    ]
    assert crm_view.observed_station_totals(series) == {
        date(2026, 1, 1): 105,
        date(2026, 1, 2): 121,
        date(2026, 1, 3): 204,
    }


def test_characterization_monthly_selection_and_downtime_window(
    monthly_report,
    downtime_records,
):
    from ppd_audit.services import crm_view

    assert crm_view.well_monthly_series(monthly_report, None) is monthly_report["totals"]
    assert crm_view.well_monthly_series(monthly_report, "100") == [
        {"month": "2025-12-01", "base": 0.0, "forecast": 0.0, "fact": None},
        {"month": "2026-01-01", "base": 20, "forecast": 30, "fact": 40},
    ]
    assert crm_view.well_monthly_series(monthly_report, "missing") == []
    assert crm_view.monthly_window(monthly_report["totals"]) == (
        datetime(2025, 12, 1),
        datetime(2026, 2, 1),
    )
    assert (
        crm_view.downtime_in_window(monthly_report["totals"], downtime_records)
        == downtime_records[1:3]
    )
    assert crm_view.downtime_in_window(monthly_report["totals"], []) == []


def test_monthly_view_filters_window_and_selected_well(monthly_report, downtime_records):
    from ppd_audit.services import crm_view

    view = crm_view.monthly_view(monthly_report, downtime_records, "100/2")
    assert view == {"series": [], "downtime_marks": [], "window": None, "last": None}
    marks = [
        {"well": "100/2", "reason": "Ремонт", "since": "2025-11-30T23:59:59"},
        {"well": "100/2", "reason": "Ремонт", "since": "2025-12-01T00:00:00"},
        {"well": "200", "reason": "Ремонт", "since": "2026-01-01T00:00:00"},
        {"well": "100/2", "reason": "Ремонт", "since": "2026-02-01T00:00:00"},
    ]
    view = crm_view.monthly_view(monthly_report, marks, "100")
    assert view["series"] == crm_view.well_monthly_series(monthly_report, "100")
    assert view["downtime_marks"] == [marks[1]]
    assert view["window"] == ["2025-12-01T00:00:00", "2026-02-01T00:00:00"]
    assert view["last"] == view["series"][-1]


def test_forecast_period_dates_follow_used_history_and_exclude_incomplete_tail(data_source):
    from ppd_audit.services.forecast_data import forecast_series

    database, *_ = data_source
    body = forecast_series(
        database, "test", "НА-1", date(2026, 1, 1), date(2026, 1, 3), period_days=1, horizon=2
    )
    assert [(point["period_start"], point["period_end"]) for point in body["history"]] == [
        ("2026-01-01", "2026-01-01"),
        ("2026-01-02", "2026-01-02"),
        ("2026-01-03", "2026-01-03"),
    ]
    assert [(point["period_start"], point["period_end"]) for point in body["forecast"]] == [
        ("2026-01-04", "2026-01-04"),
        ("2026-01-05", "2026-01-05"),
    ]
    assert body["unused_daily_count"] == 0
    assert body["missing_daily_count"] == 0


def test_forecast_dates_expose_gaps_and_unused_tail(monkeypatch):
    from ppd_audit.services import forecast_data

    rows = [(f"2026-01-{day:02}", float(day)) for day in (1, 2, 4, 5, 6, 7, 8)]
    monkeypatch.setattr(forecast_data, "daily_injection_series", lambda *args: rows)
    body = forecast_data.forecast_series(
        None, "test", "НА-1", date(2026, 1, 1), date(2026, 1, 8), period_days=2, horizon=2
    )
    assert body["history"][-1]["period_end"] == "2026-01-07"
    assert body["forecast"][0]["period_start"] == "2026-01-08"
    assert body["forecast"][-1]["period_end"] == "2026-01-11"
    assert body["unused_daily_count"] == 1
    assert body["missing_daily_count"] == 1
