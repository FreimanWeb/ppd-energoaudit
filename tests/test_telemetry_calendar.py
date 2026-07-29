from datetime import date
from importlib.resources import files

from ppd_audit.telemetry_calendar import (
    calendar_data,
    selected_calendar_date,
    visible_calendar_month,
)


def test_calendar_assets_ship_with_the_main_package():
    build_dir = files("ppd_audit.telemetry_calendar") / "frontend" / "build"

    assert len(list(build_dir.glob("index-*.js"))) == 1
    assert len(list(build_dir.glob("index-*.css"))) == 1


def test_calendar_data_serializes_telemetry_statuses():
    assert calendar_data(
        selected_day=date(2025, 7, 25),
        statuses={date(2025, 7, 24): "ready", date(2025, 7, 25): "unfit"},
    ) == {
        "value": "2025-07-25",
        "cellClasses": {"2025-07-24": "ready", "2025-07-25": "unfit"},
    }


def test_selected_calendar_date_reads_component_state(monkeypatch):
    monkeypatch.setattr(
        "ppd_audit.telemetry_calendar.st.session_state",
        {"calendar": {"selected_date": "2025-06-04"}},
    )

    assert selected_calendar_date(key="calendar", fallback=date(2025, 6, 5)) == date(2025, 6, 4)


def test_visible_calendar_month_reads_component_state(monkeypatch):
    monkeypatch.setattr(
        "ppd_audit.telemetry_calendar.st.session_state",
        {"calendar": {"visible_month": "2025-07"}},
    )

    assert visible_calendar_month(key="calendar", fallback=date(2025, 6, 5)) == (2025, 7)
