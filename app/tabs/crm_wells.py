"""Прогноз закачки по нагнетательным скважинам и взаимовлияние скважин.

Читает выгрузки CRM-модели из ``data/crm/<объект>/<прогон>/``: помесячную
закачку по каждой скважине рядом с фактом и граф взаимовлияния.
"""

from __future__ import annotations

import math
from datetime import date

import altair as alt
import lib
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import ui

from tabs.common import Ctx, fmt


SERIES = ("Базовый прогноз", "Сценарий", "Факт")
EDGE_LIMIT = 60


def _month_label(value: str) -> str:
    return date.fromisoformat(value).strftime("%m.%Y")


def _totals_frame(totals: list[dict]) -> pd.DataFrame:
    records = []
    for item in totals:
        month = _month_label(item["month"])
        records.append({"Месяц": month, "Объём": item["base"], "Ряд": SERIES[0]})
        records.append({"Месяц": month, "Объём": item["forecast"], "Ряд": SERIES[1]})
        if item["fact"] is not None:
            records.append({"Месяц": month, "Объём": item["fact"], "Ряд": SERIES[2]})
    return pd.DataFrame(records)


def _downtime_marks(totals: list[dict], downtime: list[dict]) -> pd.DataFrame:
    """Простои, начавшиеся внутри показанных месяцев, — по одной метке на месяц."""
    months = {_month_label(item["month"]) for item in totals}
    records: dict[str, list[str]] = {}
    for item in downtime:
        if not item["since"]:
            continue
        label = date.fromisoformat(item["since"]).strftime("%m.%Y")
        if label not in months:
            continue
        records.setdefault(label, []).append(
            f"{item['well']} — {item['reason']} (с {date.fromisoformat(item['since']):%d.%m})"
        )
    return pd.DataFrame(
        [
            {"Месяц": label, "Простои": len(items), "Причины": "; ".join(sorted(items))}
            for label, items in records.items()
        ]
    )


def _totals_section(report: dict, downtime: list[dict]) -> None:
    totals = report["totals"]
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

    order = [_month_label(item["month"]) for item in totals]
    chart = alt.Chart(_totals_frame(totals)).mark_line(point=True).encode(
        x=alt.X("Месяц:O", title=None, sort=order),
        y=alt.Y("Объём:Q", title="Закачка, м³/мес"),
        color=alt.Color(
            "Ряд:N",
            title=None,
            scale=alt.Scale(
                domain=list(SERIES),
                range=[ui.PALETTE["water_dark"], ui.PALETTE["accent"], ui.PALETTE["ok"]],
            ),
        ),
        tooltip=["Месяц:O", alt.Tooltip("Объём:Q", format=",.0f"), "Ряд:N"],
    )

    marks = _downtime_marks(totals, downtime)
    if not marks.empty:
        rules = alt.Chart(marks).mark_rule(
            strokeDash=[4, 4], color=ui.PALETTE["bad"], strokeWidth=1.5
        ).encode(
            x=alt.X("Месяц:O", sort=order),
            tooltip=["Месяц:O", "Простои:Q", "Причины:N"],
        )
        labels = alt.Chart(marks).mark_text(
            align="left", dx=5, dy=-6, baseline="top", color=ui.PALETTE["bad"], fontSize=11
        ).encode(
            x=alt.X("Месяц:O", sort=order),
            y=alt.value(0),
            text=alt.Text("Простои:Q", format="d"),
        )
        chart = rules + labels + chart

    st.altair_chart(chart.properties(height=320), width="stretch")
    if not marks.empty:
        st.caption(
            "Пунктир — месяц, в котором начался простой; число рядом — сколько скважин. "
            "Наведите курсор, чтобы увидеть причины."
        )


def _since(value: str | None) -> str:
    return "" if not value else f"{date.fromisoformat(value):%d.%m.%Y}"


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
    wells: list[str], edges: list[dict], selected: str, idle: set[str]
) -> go.Figure:
    """Скважины по кругу; линия — связь, толщина — сила влияния."""
    positions = {
        well: (
            math.cos(2 * math.pi * index / len(wells)),
            math.sin(2 * math.pi * index / len(wells)),
        )
        for index, well in enumerate(wells)
    }
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
                line={
                    "color": ui.PALETTE["accent"] if touches else "#e5e7eb",
                    "width": 1.0 + 2.5 * edge["strength"] if touches else 0.8,
                },
            )
        )

    figure.add_trace(
        go.Scatter(
            x=[positions[w][0] for w in wells],
            y=[positions[w][1] for w in wells],
            mode="markers+text",
            text=wells,
            textposition="middle center",
            textfont={"size": 9, "color": "#111827"},
            hovertext=[
                f"{w} — простой: {idle[w]}" if w in idle else w for w in wells
            ],
            hoverinfo="text",
            showlegend=False,
            marker={
                "size": 26,
                "color": [
                    "#cfe0f7" if w == selected else ("#eef2f7" if w in linked else "#ffffff")
                    for w in wells
                ],
                "symbol": ["square" if w in idle else "circle" for w in wells],
                "line": {
                    "color": [
                        ui.PALETTE["primary"]
                        if w == selected
                        else (ui.PALETTE["bad"] if w in idle else "#d1d5db")
                        for w in wells
                    ],
                    "width": [2 if w == selected or w in idle else 1 for w in wells],
                },
            },
        )
    )
    figure.update_layout(
        height=460,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        xaxis={"visible": False, "range": [-1.25, 1.25]},
        yaxis={"visible": False, "range": [-1.25, 1.25], "scaleanchor": "x"},
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

    keys = {lib.well_key(well): well for well in wells}
    idle = {
        keys[lib.well_key(item["well"])]: item["reason"]
        for item in downtime
        if lib.well_key(item["well"]) in keys
    }
    left, right = st.columns([1.6, 1])
    with left:
        st.plotly_chart(
            _graph_figure(wells, graph["edges"], selected, idle),
            width="stretch",
            config={"displayModeBar": False},
        )
    with right:
        neighbours = graph["by_well"].get(selected, [])
        if not neighbours:
            st.caption("У этой скважины нет сохранённых связей.")
            return
        st.markdown(f"**Связи скважины {selected}**")
        st.dataframe(
            pd.DataFrame(
                {
                    "Скважина": [item["target"] for item in neighbours],
                    "Сила": [item["strength"] for item in neighbours],
                    "Знак": [
                        "совместно" if item["signed"] >= 0 else "встречно"
                        for item in neighbours
                    ],
                }
            ),
            width="stretch",
            hide_index=True,
            column_config={"Сила": st.column_config.NumberColumn(format="%.2f")},
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
    _totals_section(report, downtime)
    st.divider()
    st.markdown("**Закачка по скважинам**")
    _wells_section(ctx, report, downtime)
    st.divider()
    st.markdown("**Взаимовлияние скважин**")
    st.caption(
        "Линия — связь по данным модели, толщина — сила влияния. "
        "Квадрат в красной рамке — скважина с причиной простоя."
    )
    _graph_section(
        ctx, report, lib.crm_wells_graph(ctx.object_id, run_code, EDGE_LIMIT), downtime
    )
