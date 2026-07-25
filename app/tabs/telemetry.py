"""📊 Телеметрия — сырые точки выбранных суток без расчётных допущений."""

from __future__ import annotations

from datetime import date

import lib
import streamlit as st
import ui

from ppd_audit.services.telemetry_series import telemetry_series
from tabs.common import Ctx


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
    for unit, frame in telemetry_series(rows).items():
        values = [column for column in frame.columns if column != "Время"]
        st.markdown(f"**{unit}**")
        st.line_chart(frame, x="Время", y=values, height=260)

    st.markdown("**Сырые точки**")
    st.dataframe(rows, hide_index=True)


def render(ctx: Ctx) -> None:
    render_day(ctx.object_id, ctx.agg_id, ctx.selected_date)
