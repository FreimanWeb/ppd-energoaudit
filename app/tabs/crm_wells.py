"""Прогноз закачки по нагнетательным скважинам и взаимовлияние скважин.

Читает выгрузки CRM-модели из ``data/crm/<объект>/<прогон>/``: помесячную
закачку по каждой скважине рядом с фактом и граф взаимовлияния.
"""

from __future__ import annotations

from datetime import date, datetime, time

import altair as alt
import lib
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import ui

from ppd_audit.report.wells_layout import spring_layout
from tabs.common import Ctx, fmt


SERIES = ("Базовый прогноз", "Сценарий", "Факт")
EDGE_LIMIT = 60
ALL_WELLS = "Все скважины (сумма)"


def _month_label(value: str) -> str:
    return date.fromisoformat(value).strftime("%m.%Y")


def _series(report: dict, well: str | None) -> list[dict]:
    """Помесячный ряд: сумма по объекту либо одна скважина."""
    if well is None:
        return report["totals"]
    return [
        {
            "month": row["month"],
            "base": row["base"] or 0.0,
            "forecast": row["forecast"] or 0.0,
            "fact": row["fact"],
        }
        for row in report["rows"]
        if row["well"] == well
    ]


def _totals_frame(totals: list[dict]) -> pd.DataFrame:
    records = []
    for item in totals:
        month = datetime.combine(date.fromisoformat(item["month"]), time.min)
        records.append({"Месяц": month, "Объём": item["base"], "Ряд": SERIES[0]})
        records.append({"Месяц": month, "Объём": item["forecast"], "Ряд": SERIES[1]})
        if item["fact"] is not None:
            records.append({"Месяц": month, "Объём": item["fact"], "Ряд": SERIES[2]})
    return pd.DataFrame(records)


def _window(totals: list[dict]) -> tuple[datetime, datetime]:
    """Период графика: от начала первого месяца до конца последнего."""
    months = [date.fromisoformat(item["month"]) for item in totals]
    last = months[-1]
    end = date(last.year + last.month // 12, last.month % 12 + 1, 1)
    return datetime.combine(months[0], time.min), datetime.combine(end, time.min)


def _downtime_marks(totals: list[dict], downtime: list[dict]) -> pd.DataFrame:
    """Простои, начавшиеся внутри показанного периода, с точным моментом."""
    first, end = _window(totals)
    records = []
    for item in downtime:
        if not item["since"]:
            continue
        moment = datetime.fromisoformat(item["since"])
        if not first <= moment < end:
            continue
        records.append(
            {
                "Момент": moment,
                "Скважина": item["well"],
                "Причина": item["reason"],
                "Начало": moment.strftime("%d.%m.%Y %H:%M"),
            }
        )
    return pd.DataFrame(records)


def _totals_section(ctx: Ctx, report: dict, downtime: list[dict]) -> None:
    choice = st.selectbox(
        "Показатель",
        [ALL_WELLS, *report["wells"]],
        key=f"crm-wells-series-{ctx.object_id}",
    )
    well = None if choice == ALL_WELLS else choice
    totals = _series(report, well)
    if not totals:
        st.info("За этот период по скважине нет строк.")
        return

    marks_source = (
        downtime
        if well is None
        else [item for item in downtime if lib.well_key(item["well"]) == lib.well_key(well)]
    )
    last = totals[-1]
    columns = st.columns(3)
    columns[0].metric(
        f"Прогноз за {_month_label(last['month'])}, м³", fmt(last["forecast"], 0)
    )
    columns[1].metric(
        "Факт, м³", fmt(last["fact"], 0) if last["fact"] is not None else "—"
    )
    if last["fact"]:
        deviation = (last["forecast"] - last["fact"]) / last["fact"] * 100.0
        columns[2].metric("Отклонение", f"{deviation:+.1f} %".replace(".", ","))

    first, end = _window(totals)
    axis = alt.Axis(
        format="%m.%Y",
        values=[datetime.combine(date.fromisoformat(item["month"]), time.min) for item in totals],
        labelAngle=0,
    )
    scale = alt.Scale(domain=[first, end])
    chart = alt.Chart(_totals_frame(totals)).mark_line(point=True).encode(
        x=alt.X("Месяц:T", title=None, axis=axis, scale=scale),
        y=alt.Y("Объём:Q", title="Закачка, м³/мес"),
        color=alt.Color(
            "Ряд:N",
            title=None,
            scale=alt.Scale(
                domain=list(SERIES),
                range=[ui.PALETTE["water_dark"], ui.PALETTE["accent"], ui.PALETTE["ok"]],
            ),
        ),
        tooltip=[
            alt.Tooltip("Месяц:T", title="Месяц", format="%m.%Y"),
            alt.Tooltip("Объём:Q", format=",.0f"),
            "Ряд:N",
        ],
    )

    marks = _downtime_marks(totals, marks_source)
    if not marks.empty:
        rules = alt.Chart(marks).mark_rule(
            strokeDash=[4, 4], color=ui.PALETTE["bad"], strokeWidth=1.5
        ).encode(
            x=alt.X("Момент:T", axis=axis, scale=scale),
            tooltip=["Скважина:N", "Причина:N", "Начало:N"],
        )
        labels = alt.Chart(marks).mark_text(
            align="left", dx=4, dy=-4, baseline="top", color=ui.PALETTE["bad"], fontSize=10
        ).encode(
            x=alt.X("Момент:T", axis=axis, scale=scale),
            y=alt.value(0),
            text="Скважина:N",
        )
        chart = chart + rules + labels

    st.altair_chart(chart.properties(height=320), width="stretch")


def _since(value: str | None) -> str:
    return "" if not value else f"{datetime.fromisoformat(value):%d.%m.%Y %H:%M}"


def _numbers(rows: list[dict], key: str, scale: float = 1.0) -> list[float | None]:
    return [None if row[key] is None else float(row[key]) * scale for row in rows]


def _texts(rows: list[dict], key: str, digits: int = 0, sign: bool = False) -> list[str]:
    """Столбец, где значение может отсутствовать.

    Числовой столбец Streamlit печатает в таких клетках «None»; для показа
    это негодно, поэтому такие столбцы выводим строками с прочерком.
    """
    out = []
    for row in rows:
        value = row[key]
        if value is None:
            out.append("—")
            continue
        text = fmt(value, digits)
        out.append(f"+{text}" if sign and value > 0 else text)
    return out


def _wells_section(ctx: Ctx, report: dict, downtime: list[dict]) -> None:
    months = report["months"]
    month = st.selectbox(
        "Месяц",
        months,
        index=len(months) - 1,
        format_func=_month_label,
        key=f"crm-wells-month-{ctx.object_id}",
    )
    rows = [row for row in report["rows"] if row["month"] == month]
    reasons = {lib.well_key(item["well"]): item for item in downtime}
    frame = pd.DataFrame(
        {
            "Скважина": [row["well"] for row in rows],
            "Прогноз, м³/мес": _numbers(rows, "forecast"),
            "Факт, м³/мес": _texts(rows, "fact"),
            "Отклонение, %": _texts(rows, "deviation", digits=1, sign=True),
            "Доля, %": _numbers(rows, "share", scale=100.0),
            "Руст, атм": _numbers(rows, "r_ust"),
            "Причина простоя": [
                reasons.get(lib.well_key(row["well"]), {}).get("reason", "") for row in rows
            ],
            "Простой с": [
                _since(reasons.get(lib.well_key(row["well"]), {}).get("since"))
                for row in rows
            ],
        }
    )
    st.dataframe(
        frame.sort_values("Прогноз, м³/мес", ascending=False),
        width="stretch",
        hide_index=True,
        column_config={
            "Прогноз, м³/мес": st.column_config.NumberColumn(format="%.0f"),
            "Доля, %": st.column_config.NumberColumn(format="%.2f"),
            "Руст, атм": st.column_config.NumberColumn(format="%.0f"),
        },
    )


def _graph_figure(
    wells: list[str], edges: list[dict], selected: str, idle: set[str], limit: float
) -> go.Figure:
    """Граф связей: раскладка силами, цвет и толщина — сила связи.

    Шкала своя у каждой скважины: у одних сильнейшая связь 0,8, у других 0,2,
    и общая шкала красила бы половину объектов в один оттенок.
    """
    positions = spring_layout(
        wells, [(edge["source"], edge["target"], edge["strength"]) for edge in edges]
    )
    linked = {
        edge["target"] if edge["source"] == selected else edge["source"]
        for edge in edges
        if selected in (edge["source"], edge["target"])
    }

    figure = go.Figure()
    for edge in edges:
        if edge["source"] not in positions or edge["target"] not in positions:
            continue
        x0, y0 = positions[edge["source"]]
        x1, y1 = positions[edge["target"]]
        touches = selected in (edge["source"], edge["target"])
        figure.add_trace(
            go.Scatter(
                x=[x0, x1],
                y=[y0, y1],
                mode="lines",
                hoverinfo="skip",
                showlegend=False,
                opacity=1.0 if touches else 0.45,
                line={
                    "color": (
                        ui.strength_color(edge["strength"], limit) if touches else "#e5e7eb"
                    ),
                    "width": 1.0 + 3.0 * edge["strength"] if touches else 0.9,
                },
            )
        )

    figure.add_trace(
        go.Scatter(
            x=[positions[w][0] for w in wells],
            y=[positions[w][1] for w in wells],
            mode="markers+text",
            text=wells,
            textposition="bottom center",
            textfont={"size": 9, "color": "#111827"},
            hovertext=[
                f"{w} — простой: {idle[w]}" if w in idle else w for w in wells
            ],
            hoverinfo="text",
            showlegend=False,
            marker={
                "size": [18 if w == selected else 13 for w in wells],
                "color": [
                    "#cfe0f7" if w == selected else ("#eef2f7" if w in linked else "#ffffff")
                    for w in wells
                ],
                "symbol": ["square" if w in idle else "circle" for w in wells],
                "line": {
                    "color": [
                        ui.PALETTE["primary"]
                        if w == selected
                        else (ui.PALETTE["muted"] if w in idle else "#d1d5db")
                        for w in wells
                    ],
                    "width": [2 if w == selected or w in idle else 1 for w in wells],
                },
            },
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="markers",
            hoverinfo="skip",
            showlegend=False,
            marker={
                "colorscale": [list(stop) for stop in ui.SEQUENTIAL],
                "cmin": 0.0,
                "cmax": limit,
                "color": [0],
                "showscale": True,
                "colorbar": {
                    "orientation": "h",
                    "y": -0.02,
                    "x": 0.5,
                    "thickness": 8,
                    "len": 0.55,
                    "tickvals": [0.0, limit],
                    "ticktext": ["слабая", f"сильная ({limit:.2f})".replace(".", ",")],
                    "tickfont": {"size": 10},
                    "outlinewidth": 0,
                },
            },
        )
    )
    figure.update_layout(
        height=560,
        margin={"l": 10, "r": 10, "t": 10, "b": 44},
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        xaxis={"visible": False, "range": [-1.15, 1.15]},
        yaxis={"visible": False, "range": [-1.15, 1.15], "scaleanchor": "x"},
    )
    return figure


def _graph_section(ctx: Ctx, report: dict, graph: dict, downtime: list[dict]) -> None:
    if not graph or not graph["edges"]:
        st.caption("Связи скважин в этом прогоне не сохранены.")
        return

    ranked = [item["well"] for item in graph["centrality"]]
    wells = ranked + [well for well in report["wells"] if well not in ranked]
    selected = st.selectbox(
        "Скважина", wells, key=f"crm-wells-graph-{ctx.object_id}"
    )

    neighbours = graph["by_well"].get(selected, [])
    limit = max((item["strength"] for item in neighbours), default=0.0)
    keys = {lib.well_key(well): well for well in wells}
    idle = {
        keys[lib.well_key(item["well"])]: item["reason"]
        for item in downtime
        if lib.well_key(item["well"]) in keys
    }
    left, right = st.columns([1.6, 1])
    with left:
        st.plotly_chart(
            _graph_figure(wells, graph["edges"], selected, idle, limit),
            width="stretch",
            config={"displayModeBar": False},
        )
    with right:
        if not neighbours:
            st.caption("У этой скважины нет сохранённых связей.")
            return
        st.markdown(f"**Связи скважины {selected}**")
        colors = [ui.strength_color(item["strength"], limit) for item in neighbours]
        frame = pd.DataFrame(
            {
                "Скважина": [item["target"] for item in neighbours],
                "Сила": [item["strength"] for item in neighbours],
            }
        )
        st.dataframe(
            frame.style.format({"Сила": "{:.2f}"}).apply(
                lambda _: [f"background-color: {color}" for color in colors],
                subset=["Сила"],
            ),
            width="stretch",
            hide_index=True,
        )


def render(ctx: Ctx) -> None:
    st.subheader("Прогноз закачки по скважинам")

    runs = lib.crm_well_runs(ctx.object_id)
    if not runs:
        st.info("Нет данных прогноза по скважинам для этого объекта.")
        return

    if len(runs) > 1:
        titles = {run["title"]: run["code"] for run in runs}
        run_code = titles[
            st.radio("Прогон", list(titles), horizontal=True, key=f"crm-wells-run-{ctx.object_id}")
        ]
    else:
        run_code = runs[0]["code"]
    report = lib.crm_wells_report(ctx.object_id, run_code)
    if report is None:
        st.warning("Прогон не найден. Обновите страницу.")
        return
    if "error" in report:
        st.error(f"Выгрузка не читается: {report['error']}")
        return

    badges = [(f"Скважин: {len(report['wells'])}", "")]
    if not report["has_fact"]:
        badges.append(("Факта за период нет", "warn"))
    ui.provenance(*badges)

    downtime = lib.well_downtime(ctx.object_id)
    _totals_section(ctx, report, downtime)
    st.divider()
    st.markdown("**Закачка по скважинам**")
    _wells_section(ctx, report, downtime)
    st.divider()
    st.markdown("**Взаимовлияние скважин**")
    st.caption("Цвет и толщина — сила связи; квадрат — скважина с причиной простоя.")
    _graph_section(
        ctx, report, lib.crm_wells_graph(ctx.object_id, run_code, EDGE_LIMIT), downtime
    )
