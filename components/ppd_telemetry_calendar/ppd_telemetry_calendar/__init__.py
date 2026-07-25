from __future__ import annotations

from datetime import date

import streamlit as st


_CALENDAR = None


def _calendar_renderer():
    global _CALENDAR
    if _CALENDAR is None:
        _CALENDAR = st.components.v2.component(
            "ppd-telemetry-calendar.telemetry_calendar",
            js="index-*.js",
            css="index-*.css",
            html='<div class="react-root"></div>',
            isolate_styles=False,
        )
    return _CALENDAR


def calendar_data(selected_day: date, statuses: dict[date, str]) -> dict[str, object]:
    return {
        "value": selected_day.isoformat(),
        "cellClasses": {day.isoformat(): status for day, status in statuses.items()},
    }


def selected_calendar_date(*, key: str, fallback: date) -> date:
    component_state = st.session_state.get(key, {})
    try:
        return date.fromisoformat(component_state.get("selected_date"))
    except (AttributeError, TypeError, ValueError):
        return fallback


def render_calendar(
    *,
    selected_day: date,
    statuses: dict[date, str],
    min_day: date,
    max_day: date,
    key: str,
) -> date:
    data = calendar_data(selected_day, statuses)
    data["minDate"] = min_day.isoformat()
    data["maxDate"] = max_day.isoformat()
    _calendar_renderer()(
        key=key,
        data=data,
    )
    return selected_day
