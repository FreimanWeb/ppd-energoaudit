from datetime import date

from ppd_telemetry_calendar import calendar_data, selected_calendar_date


def test_calendar_data_serializes_telemetry_statuses():
    assert calendar_data(
        selected_day=date(2025, 7, 25),
        statuses={date(2025, 7, 24): "ready", date(2025, 7, 25): "insufficient"},
    ) == {
        "value": "2025-07-25",
        "cellClasses": {"2025-07-24": "ready", "2025-07-25": "insufficient"},
    }


def test_selected_calendar_date_reads_component_state(monkeypatch):
    monkeypatch.setattr(
        "ppd_telemetry_calendar.st.session_state",
        {"calendar": {"selected_date": "2025-06-04"}},
    )

    assert selected_calendar_date(key="calendar", fallback=date(2025, 6, 5)) == date(2025, 6, 4)
