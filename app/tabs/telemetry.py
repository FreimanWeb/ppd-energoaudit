"""📊 Телеметрия — сырые точки выбранных суток без расчётных допущений."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import altair as alt
import lib
import streamlit as st
import ui

from ppd_audit.services.telemetry_series import telemetry_series
from tabs.common import Ctx


def _line_chart(frame, *, day: date | None = None):
    x = alt.X(
        "Время:T",
        title=None,
        axis=alt.Axis(format="%H:%M" if day else "%d.%m %H:%M"),
    )
    if day:
        x = x.scale(
            domain=[
                datetime.combine(day, time.min),
                datetime.combine(day + timedelta(days=1), time.min),
            ]
        )
    return (
        alt.Chart(frame)
        .mark_line(point=True)
        .encode(
            x=x,
            y=alt.Y("Значение:Q"),
            color=alt.Color("Показатель:N"),
            tooltip=[
                alt.Tooltip("Время:T", format="%d.%m.%Y %H:%M:%S"),
                "Показатель:N",
                "Значение:Q",
            ],
        )
        .properties(height=260)
    )


def _render_charts(rows: list[dict], *, day: date | None = None) -> None:
    for unit, frame in telemetry_series(rows).items():
        st.markdown(f"**{unit}**")
        st.altair_chart(_line_chart(frame, day=day), width="stretch")


def render_day(object_id: str, aggregate_id: str, selected_date: date) -> None:
    st.subheader("Телеметрия за сутки")
    ui.provenance(("Сырые измерения SQLite", "ok"))
    rows = lib.telemetry_for_day(object_id, aggregate_id, selected_date)
    if not rows:
        st.info("За выбранные сутки нет точек телеметрии.")
        return

    st.caption(
        "На графиках только измеряемые сигналы. Пропуски не заменяются нулями; "
        "показатели станции отмечены отдельно. Q_сут, моточасы и W отдельно не строятся."
    )
    _render_charts(rows, day=selected_date)


def render_period(object_id: str, aggregate_id: str, start_date: date, end_date: date) -> None:
    st.subheader("Телеметрия за период")
    ui.provenance(("Сырые измерения SQLite", "ok"))
    rows = lib.telemetry_for_period(object_id, aggregate_id, start_date, end_date)
    if not rows:
        st.info("В выбранном периоде нет точек телеметрии.")
        return

    st.caption(
        "На графиках только измеряемые сигналы. Пропуски не заменяются нулями; "
        "показатели станции отмечены отдельно."
    )
    _render_charts(rows)


def render(ctx: Ctx) -> None:
    render_day(ctx.object_id, ctx.agg_id, ctx.selected_date)
