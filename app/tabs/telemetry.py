"""📊 Телеметрия — сырые точки выбранных суток без расчётных допущений."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import altair as alt
import lib
import pandas as pd
import streamlit as st
import ui

from ppd_audit.services.telemetry_series import telemetry_series
from tabs.common import Ctx


def _reduce_pressure_points(frame: pd.DataFrame) -> pd.DataFrame:
    """Сохранить границы и экстремумы каждой минуты для каждого показателя."""
    points = frame.assign(_bucket=frame["Время"].dt.floor("min"))
    groups = points.groupby(["Показатель", "_bucket"], group_keys=False)
    extreme_indices = pd.concat([groups["Значение"].idxmin(), groups["Значение"].idxmax()])
    return (
        pd.concat([groups.head(1), points.loc[extreme_indices], groups.tail(1)])
        .drop_duplicates(subset=["Показатель", "Время"])
        .sort_values(["Показатель", "Время"])
        .drop(columns="_bucket")
        .reset_index(drop=True)
    )


def _line_chart(frame, *, day: date | None = None, pressure: bool = False):
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
        .mark_line(point=True, interpolate="step-after" if pressure else "linear")
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
        .properties(height=260, padding={"top": 12, "right": 24})
        .add_params(alt.selection_interval(bind="scales"))
        .configure_legend(orient="bottom", direction="horizontal")
    )


def _render_charts(
    rows: list[dict], *, start: datetime, end: datetime, day: date | None = None
) -> None:
    series = telemetry_series(rows, start=start, end=end)
    for unit, frame in sorted(series.items(), key=lambda item: item[0] != "кВт"):
        st.markdown(f"**{unit}**")
        display_frame = _reduce_pressure_points(frame) if unit == "МПа" else frame
        st.altair_chart(
            _line_chart(display_frame, day=day, pressure=unit in {"МПа", "кВт"}),
            width="stretch",
        )


def render_day(object_id: str, aggregate_id: str, selected_date: date) -> None:
    st.subheader("Телеметрия за сутки")
    ui.provenance(("Сырые измерения SQLite", "ok"))
    rows = lib.telemetry_for_day(object_id, aggregate_id, selected_date)
    if not rows:
        st.info("За выбранные сутки нет точек телеметрии.")
        return

    st.caption(
        "Давления и мощность показаны ступенями: значение действует до следующего изменения. "
        "Точки давления для читаемости сведены к границам, минимуму и максимуму каждой минуты; "
        "расчёты используют исходные данные. Q_сут, наработка и W не строятся."
    )
    start = datetime.combine(selected_date, time.min)
    _render_charts(rows, start=start, end=start + timedelta(days=1), day=selected_date)


def render_period(object_id: str, aggregate_id: str, start_date: date, end_date: date) -> None:
    st.subheader("Телеметрия за период")
    ui.provenance(("Сырые измерения SQLite", "ok"))
    rows = lib.telemetry_for_period(object_id, aggregate_id, start_date, end_date)
    if not rows:
        st.info("В выбранном периоде нет точек телеметрии.")
        return

    st.caption(
        "Давления и мощность показаны ступенями: значение действует до следующего изменения. "
        "Точки давления для читаемости сведены к границам, минимуму и максимуму каждой минуты; "
        "показатели станции отмечены отдельно."
    )
    start = datetime.combine(start_date, time.min)
    end = datetime.combine(end_date + timedelta(days=1), time.min)
    _render_charts(rows, start=start, end=end)


def render(ctx: Ctx) -> None:
    render_day(ctx.object_id, ctx.agg_id, ctx.selected_date)
