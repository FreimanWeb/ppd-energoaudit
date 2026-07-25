"""📊 Телеметрия — сырые точки выбранных суток без расчётных допущений."""

from __future__ import annotations

from datetime import date

import lib
import streamlit as st
import ui

from ppd_audit.services.telemetry_series import telemetry_series
from tabs.common import Ctx


def _render_charts(rows: list[dict]) -> None:
    for unit, frame in telemetry_series(rows).items():
        values = [column for column in frame.columns if column != "Время"]
        st.markdown(f"**{unit}**")
        st.line_chart(frame, x="Время", y=values, height=260)


def render_day(object_id: str, aggregate_id: str, selected_date: date) -> None:
    st.subheader("Телеметрия за сутки")
    ui.provenance(("Сырые измерения SQLite", "ok"))
    rows = lib.telemetry_for_day(object_id, aggregate_id, selected_date)
    if not rows:
        st.info("За выбранные сутки нет точек телеметрии.")
        return

    st.caption(
        "На графиках только измеряемые сигналы. Пропуски не заменяются нулями; "
        "показатели станции отмечены отдельно. Q_сут, моточасы и W — в таблице ниже."
    )
    _render_charts(rows)

    st.markdown("**Сырые точки**")
    st.dataframe(rows, hide_index=True)


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
