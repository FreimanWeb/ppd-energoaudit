import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from ppd_audit.db import AuditDatabase
from ppd_audit.services.telemetry_series import telemetry_series


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import lib
import tabs.telemetry as telemetry
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


def test_telemetry_series_carries_pressure_to_the_visible_window_start():
    start = datetime(2026, 7, 24)
    series = telemetry_series(
        [
            {
                "timestamp": "2026-07-23T23:59:59",
                "metric": "p_in",
                "value": 1.2,
                "unit": "МПа",
                "is_station": 0,
            },
            {
                "timestamp": "2026-07-24T00:00:10",
                "metric": "p_in",
                "value": 1.4,
                "unit": "МПа",
                "is_station": 0,
            },
        ],
        start=start,
        end=start + timedelta(days=1),
    )

    p_in = series["МПа"].query("Показатель == 'p_вх'")

    assert list(p_in["Время"]) == [
        start,
        start + timedelta(seconds=10),
        start + timedelta(days=1),
    ]
    assert list(p_in["Значение"]) == [1.2, 1.4, 1.4]


def test_telemetry_series_extends_held_state_to_the_visible_window_end():
    start = datetime(2026, 7, 24)
    end = start + timedelta(days=1)
    series = telemetry_series(
        [
            {
                "timestamp": start.isoformat(),
                "metric": "p_in",
                "value": 1.2,
                "unit": "МПа",
                "is_station": 0,
            }
        ],
        start=start,
        end=end,
    )

    p_in = series["МПа"].query("Показатель == 'p_вх'")

    assert list(p_in["Время"]) == [start, end]
    assert list(p_in["Значение"]) == [1.2, 1.2]


def test_telemetry_series_carries_power_to_the_visible_window_start():
    start = datetime(2026, 7, 24)
    series = telemetry_series(
        [
            {
                "timestamp": (start - timedelta(minutes=30)).isoformat(),
                "metric": "power",
                "value": 210.0,
                "unit": "кВт",
                "is_station": 0,
            }
        ],
        start=start,
        end=start + timedelta(days=1),
    )

    assert series["кВт"].iloc[0].to_dict() == {
        "Время": start,
        "Показатель": "P_эл",
        "Значение": 210.0,
    }


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


def test_telemetry_chart_allows_scale_zoom():
    frame = telemetry_series([
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "p_in",
            "value": 1.2,
            "unit": "МПа",
            "is_station": 0,
        }
    ])["МПа"]

    params = _line_chart(frame).to_dict().get("params", [])

    assert any(param.get("bind") == "scales" for param in params)


def test_telemetry_charts_show_power_before_pressure(monkeypatch):
    frame = pd.DataFrame(
        {
            "Время": [datetime(2026, 7, 24)],
            "Показатель": ["P_эл"],
            "Значение": [250.0],
        }
    )
    headings = []
    monkeypatch.setattr(telemetry, "telemetry_series", lambda *_args, **_kwargs: {
        "МПа": frame,
        "кВт": frame,
    })
    monkeypatch.setattr(telemetry.st, "markdown", headings.append)
    monkeypatch.setattr(telemetry.st, "altair_chart", lambda *_args, **_kwargs: None)

    telemetry._render_charts([], start=datetime(2026, 7, 24), end=datetime(2026, 7, 25))

    assert headings == ["**кВт**", "**МПа**"]


def test_pressure_chart_display_keeps_minimum_and_maximum_per_minute():
    frame = pd.DataFrame(
        {
            "Время": [
                datetime(2026, 7, 24, 17, 0, 0),
                datetime(2026, 7, 24, 17, 0, 1),
                datetime(2026, 7, 24, 17, 0, 8),
                datetime(2026, 7, 24, 17, 0, 9),
                datetime(2026, 7, 24, 17, 0, 59),
            ],
            "Показатель": ["p_вх"] * 5,
            "Значение": [10.0, 12.0, 8.0, 10.3, 10.4],
        }
    )

    reduced = getattr(telemetry, "_reduce_pressure_points", lambda value: value)(frame)

    assert list(reduced["Время"]) == [
        datetime(2026, 7, 24, 17, 0, 0),
        datetime(2026, 7, 24, 17, 0, 1),
        datetime(2026, 7, 24, 17, 0, 8),
        datetime(2026, 7, 24, 17, 0, 59),
    ]


def test_telemetry_chart_places_legend_below_plot():
    frame = telemetry_series([
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "power",
            "value": 250.0,
            "unit": "кВт",
            "is_station": 0,
        }
    ])["кВт"]

    legend = _line_chart(frame).to_dict()["config"]["legend"]

    assert legend == {"orient": "bottom", "direction": "horizontal"}


def test_telemetry_chart_adds_top_and_right_padding():
    frame = telemetry_series([
        {
            "timestamp": "2026-07-24T00:00:00",
            "metric": "power",
            "value": 250.0,
            "unit": "кВт",
            "is_station": 0,
        }
    ])["кВт"]

    assert _line_chart(frame).to_dict()["padding"] == {"top": 12, "right": 24}


def test_daily_telemetry_chart_uses_24_hour_axis_and_day_bounds():
    frame = telemetry_series([
        {
            "timestamp": "2026-07-24T10:00:00",
            "metric": "power",
            "value": 250.0,
            "unit": "кВт",
            "is_station": 0,
        }
    ])["кВт"]

    x = _line_chart(frame, day=date(2026, 7, 24)).to_dict()["encoding"]["x"]

    assert x["axis"]["format"] == "%H:%M"
    assert x["scale"]["domain"] == [
        {"year": 2026, "month": 7, "date": 24},
        {"year": 2026, "month": 7, "date": 25},
    ]


def test_daily_telemetry_view_does_not_render_raw_points_table():
    source = (Path(__file__).resolve().parents[1] / "app" / "tabs" / "telemetry.py").read_text(
        encoding="utf-8"
    )

    assert 'st.markdown("**Сырые точки**")' not in source


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

    assert [row["value"] for row in rows] == [200.0, 210.0, 220.0]
