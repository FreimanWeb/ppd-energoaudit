"""Characterization и parity перенесённого data-слоя на локальных fixtures."""

import json
import sys
from datetime import date, datetime, timedelta
from importlib import import_module, util
from pathlib import Path

import pytest

from ppd_audit.db import AuditDatabase


@pytest.fixture
def data_source(tmp_path, monkeypatch):
    sys.path.insert(0, "app")
    lib = import_module("lib")
    db = AuditDatabase(tmp_path / "data.sqlite")
    db.migrate()
    db.upsert_plant("test", "КНС тест", "НГДУ", "пресная", "кнс")
    db.upsert_aggregate("test", "НА-1", "работа")
    start = datetime(2026, 1, 1)
    db.add_measurement("test", "НА-1", start - timedelta(hours=1), "p_in", 1, "МПа")
    for index in range(3):
        stamp = start + timedelta(days=index)
        db.add_measurement("test", None, stamp, "q_day", 100 + index, "м³/сут")
    db.add_measurement("test", "НА-1", start + timedelta(days=1), "q_day", 20, "м³/сут")
    db.add_measurement("test", "НА-1", start + timedelta(days=2), "p_in", 2, "МПа")
    monkeypatch.setattr(lib, "database", lambda: db)
    crm = tmp_path / "crm"
    run = crm / "test" / "daily"
    run.mkdir(parents=True)
    (run / "model_metadata.json").write_text(json.dumps({"object_id": "001"}))
    header = "datetime,PRED::PUMP_001_QVD_I3,Q_OUT_SUM\n"
    rows = [f"2026-01-01 {hour:02}:00:00,2,2" for hour in range(24)]
    (run / "forecast_by_equipment_and_total.csv").write_text(header + "\n".join(rows))
    tags = tmp_path / "tags.yaml"
    tags.write_text("objects:\n  '001':\n    aggregates: {PUMP_001: НА-1}\n")
    monkeypatch.setattr(lib, "CRM_DIR", crm)
    monkeypatch.setattr(lib, "SCADA_TAGS", tags)
    monkeypatch.setattr(lib, "DOWNTIME_DIR", tmp_path / "downtime")
    for name in ["crm_runs", "crm_daily_forecast", "crm_well_runs", "well_downtime"]:
        getattr(lib, name).clear()
    return lib, db, crm, tags


def test_characterization_station_priority_and_inclusive_window(data_source):
    lib, *_ = data_source
    assert lib.daily_injection_series("test", "НА-1", date(2026, 1, 1), date(2026, 1, 3)) == [
        ("2026-01-01", 100),
        ("2026-01-02", 20),
        ("2026-01-03", 102),
    ]
    rows = lib.telemetry_for_period("test", "НА-1", date(2026, 1, 1), date(2026, 1, 2))
    assert any(row["timestamp"] == "2025-12-31T23:00:00" for row in rows)
    assert not any(
        row["metric"] == "q_day" and row["timestamp"].startswith("2026-01-03") for row in rows
    )
    assert any(
        row["metric"] == "p_in" and row["timestamp"].startswith("2026-01-03") for row in rows
    )
    assert lib.injection_profile("test", "НА-1", 1000, period_days=30) is None


def test_characterization_crm_mapping_missing_run_and_source_error(data_source):
    lib, _, crm, _ = data_source
    result = lib.crm_daily_forecast("test", "daily")
    assert result["by_unit"] == {"НА-1": [("2026-01-01", 48.0)]}
    assert result["total"] == [("2026-01-01", 48.0)]
    assert lib.crm_daily_forecast("test", "absent") is None
    assert lib.well_downtime("test") == []
    (crm / "test" / "daily" / "forecast_by_equipment_and_total.csv").write_text("bad,data\n")
    lib.crm_daily_forecast.clear()
    assert "error" in lib.crm_daily_forecast("test", "daily")


@pytest.mark.parametrize("name", ["catalog", "telemetry_view", "crm_view", "forecast_data"])
def test_neutral_services_exist_without_ui_imports(name):
    module_name = f"ppd_audit.services.{name}"
    assert util.find_spec(module_name) is not None, "data-логика должна быть вынесена из app/lib.py"
    module = import_module(module_name)
    source = Path(module.__file__).read_text()
    assert "import streamlit" not in source
    assert "import plotly" not in source


def test_service_parity(data_source):
    for name in ["telemetry_view", "crm_view", "forecast_data", "catalog"]:
        assert util.find_spec(f"ppd_audit.services.{name}") is not None
    telemetry = import_module("ppd_audit.services.telemetry_view")
    crm_view = import_module("ppd_audit.services.crm_view")
    forecast = import_module("ppd_audit.services.forecast_data")
    catalog = import_module("ppd_audit.services.catalog")
    lib, db, crm, tags = data_source
    days = date(2026, 1, 1), date(2026, 1, 3)
    assert telemetry.daily_injection_series(
        db, "test", "НА-1", *days
    ) == lib.daily_injection_series("test", "НА-1", *days)
    assert telemetry.telemetry_for_period(db, "test", "НА-1", *days) == lib.telemetry_for_period(
        "test", "НА-1", *days
    )
    assert crm_view.crm_daily_forecast(crm, tags, "test", "daily") == lib.crm_daily_forecast(
        "test", "daily"
    )
    assert catalog.object_index(db) == lib.object_index()
    assert forecast.injection_profile(db, "test", "НА-1", 1000, period_days=30) is None


def test_crm_source_errors_are_returned_as_data(data_source):
    from ppd_audit.services import crm_view

    _, _, crm, tags = data_source
    tags.unlink()
    assert "error" in crm_view.crm_daily_forecast(crm, tags, "test", "daily")


def test_forecast_service_returns_canonical_history_and_core_results(data_source):
    from ppd_audit.services import forecast_data

    assert hasattr(forecast_data, "forecast_series")
    _, db, *_ = data_source
    body = forecast_data.forecast_series(
        db,
        "test",
        "НА-1",
        date(2026, 1, 1),
        date(2026, 1, 3),
        period_days=1,
        horizon=2,
    )
    assert body["history"] == [
        {"period": -2, "value": 100},
        {"period": -1, "value": 20},
        {"period": 0, "value": 102},
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

    _, _, crm, _ = data_source
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

    assert hasattr(catalog, "source_paths")
    monkeypatch.setenv("PPD_CRM_DIR", str(tmp_path / "custom-crm"))
    monkeypatch.setenv("PPD_DOWNTIME_DIR", str(tmp_path / "custom-downtime"))
    monkeypatch.setenv("PPD_SCADA_TAGS_PATH", str(tmp_path / "custom.yaml"))
    paths = catalog.source_paths(tmp_path)
    assert paths == {
        "crm": tmp_path / "custom-crm",
        "downtime": tmp_path / "custom-downtime",
        "scada_tags": tmp_path / "custom.yaml",
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
def test_forecast_reports_insufficient_counts_for_both_interfaces(
    data_source,
    end,
    period_days,
    daily_count,
    period_count,
):
    from ppd_audit.services import forecast_data

    assert hasattr(forecast_data, "InsufficientForecastData")
    _, database, *_ = data_source
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
    lib, db, *_ = data_source
    db.upsert_aggregate("test", "НА-2", "работа")
    db.add_measurement("test", "НА-2", datetime(2026, 1, 1), "q_day", 5, "м³/сут")
    from tabs import crm

    assert crm._fact_series("test", ["НА-1", "НА-2"], date(2026, 1, 1), date(2026, 1, 3)) == {
        date(2026, 1, 1): 105,
        date(2026, 1, 2): 121,
        date(2026, 1, 3): 204,
    }


def test_characterization_monthly_selection_and_downtime_window(
    data_source,
    monthly_report,
    downtime_records,
):
    from tabs import crm_wells

    assert crm_wells._series(monthly_report, None) is monthly_report["totals"]
    assert crm_wells._series(monthly_report, "100") == [
        {"month": "2025-12-01", "base": 0.0, "forecast": 0.0, "fact": None},
        {"month": "2026-01-01", "base": 20, "forecast": 30, "fact": 40},
    ]
    assert crm_wells._series(monthly_report, "missing") == []
    assert crm_wells._window(monthly_report["totals"]) == (
        datetime(2025, 12, 1),
        datetime(2026, 2, 1),
    )
    marks = crm_wells._downtime_marks(monthly_report["totals"], downtime_records)
    assert marks.to_dict(orient="records") == [
        {
            "Момент": datetime(2025, 12, 1),
            "Скважина": "1",
            "Причина": "Ремонт",
            "Начало": "01.12.2025 00:00",
        },
        {
            "Момент": datetime(2026, 1, 31, 23, 59, 59),
            "Скважина": "2",
            "Причина": "Ремонт",
            "Начало": "31.01.2026 23:59",
        },
    ]
    assert crm_wells._downtime_marks(monthly_report["totals"], []).empty


def test_crm_preparation_is_shared(data_source, monthly_report, downtime_records, monkeypatch):
    from tabs import crm, crm_wells

    from ppd_audit.services import crm_view

    for name in [
        "observed_station_totals",
        "well_monthly_series",
        "monthly_window",
        "downtime_in_window",
    ]:
        assert hasattr(crm_view, name), "подготовка данных должна быть общей для интерфейсов"
    calls = []
    for name in [
        "observed_station_totals",
        "well_monthly_series",
        "monthly_window",
        "downtime_in_window",
    ]:
        original = getattr(crm_view, name)

        def trace(*args, _name=name, _original=original, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(crm_view, name, trace)
    crm._fact_series("test", ["НА-1"], date(2026, 1, 1), date(2026, 1, 3))
    crm_wells._series(monthly_report, "100")
    crm_wells._window(monthly_report["totals"])
    crm_wells._downtime_marks(monthly_report["totals"], downtime_records)
    assert set(calls) == {
        "observed_station_totals",
        "well_monthly_series",
        "monthly_window",
        "downtime_in_window",
    }
    assert (
        crm_view.downtime_in_window(monthly_report["totals"], downtime_records)
        == downtime_records[1:3]
    )


def test_monthly_view_filters_window_and_selected_well(monthly_report, downtime_records):
    from ppd_audit.services import crm_view

    assert hasattr(crm_view, "monthly_view")
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
