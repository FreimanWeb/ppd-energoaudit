import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from ppd_audit.db import AuditDatabase
from ppd_audit.services.telemetry_series import telemetry_series


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import lib
from tabs.telemetry import _line_chart


def test_telemetry_series_groups_metrics_by_unit_and_keeps_zero_values():
    series = telemetry_series([
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "p_in",
            "value": 1.2,
            "unit": "МПа",
            "is_station": 0,
        },
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "p_bg",
            "value": 0.0,
            "unit": "МПа",
            "is_station": 1,
        },
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "power",
            "value": 250.0,
            "unit": "кВт",
            "is_station": 0,
        },
    ])

    pressure = series["МПа"].set_index("Показатель")
    assert pressure.loc["p_вх", "Значение"] == 1.2
    assert pressure.loc["p_БГ (станция)", "Значение"] == 0.0
    assert series["кВт"].loc[0, "Значение"] == 250.0


def test_telemetry_series_keeps_each_metric_without_timestamp_gaps():
    series = telemetry_series([
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "p_in",
            "value": 1.2,
            "unit": "МПа",
            "is_station": 0,
        },
        {
            "timestamp": "2026-07-24T00:00:30",
            "metric": "p_out",
            "value": 10.0,
            "unit": "МПа",
            "is_station": 0,
        },
        {
            "timestamp": "2026-07-24T00:01:00",
            "metric": "p_in",
            "value": 1.4,
            "unit": "МПа",
            "is_station": 0,
        },
    ])

    p_in = series["МПа"].query("Показатель == 'p_вх'")

    assert list(p_in["Значение"]) == [1.2, 1.4]
    assert p_in["Значение"].notna().all()


def test_telemetry_series_excludes_daily_totals_from_charts():
    series = telemetry_series([
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "q_day",
            "value": 2400.0,
            "unit": "м³/сут",
            "is_station": 0,
        },
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "runtime",
            "value": 24.0,
            "unit": "ч",
            "is_station": 0,
        },
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "energy",
            "value": 4800.0,
            "unit": "кВт·ч",
            "is_station": 0,
        },
    ])

    assert series == {}


def test_telemetry_chart_marks_each_measurement_point():
    frame = telemetry_series([
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "p_in",
            "value": 1.2,
            "unit": "МПа",
            "is_station": 0,
        }
    ])["МПа"]

    assert _line_chart(frame).to_dict()["mark"]["point"] is True


def test_telemetry_for_period_includes_both_selected_days(monkeypatch, tmp_path):
    database = AuditDatabase(tmp_path / "audit.sqlite")
    database.migrate()
    database.upsert_plant("kns97", "КНС-97", "Елховнефть", "пресная", "кнс")
    database.upsert_aggregate("kns97", "НА-02", "работа")
    start = datetime(2026, 7, 24)
    database.add_measurement("kns97", "НА-02", start, "power", 200.0, "кВт")
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(days=1), "power", 210.0, "кВт"
    )
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(days=2), "power", 220.0, "кВт"
    )
    monkeypatch.setattr(lib, "database", lambda: database)

    rows = lib.telemetry_for_period(
        "kns97", "НА-02", date(2026, 7, 24), date(2026, 7, 25)
    )

    assert [row["value"] for row in rows] == [200.0, 210.0]
