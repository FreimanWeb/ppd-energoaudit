"""Рабочая точка — Q-H (насос × трубопровод) и Q-η с фактической точкой."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st
import ui

from ppd_audit.services.analysis import working_point
from tabs.common import Ctx, fmt


def render(ctx: Ctx) -> None:
    st.subheader("Рабочая точка: насос × трубопровод")
    ui.provenance(("Паспортная или модельная кривая", "warn"))
    curves = working_point(ctx.audit)
    point, nominal = curves["point"], curves["nominal"]
    q_work = point["q"]
    volumetric = curves["pump_kind"] == "объёмный"
    if volumetric:
        st.caption("Плунжерный насос: паспортная кривая Q-H неприменима, показаны факт. точки.")

    cc = st.columns(2)
    with cc[0]:
        fig = go.Figure()
        if curves["qh"]:
            qs = [item["q"] for item in curves["qh"]]
            hs = [item["h"] for item in curves["qh"]]
            is_pass = curves["origin"]["qh"] == "passport"
            fig.add_trace(
                go.Scatter(
                    x=qs,
                    y=hs,
                    mode="lines",
                    name="Кривая насоса · паспорт" if is_pass else "Кривая насоса · модель",
                    line={"color": "#1f4e79", "width": 3, "dash": None if is_pass else "dot"},
                )
            )
        if curves["system"]:
            fig.add_trace(
                go.Scatter(
                    x=[item["q"] for item in curves["system"]],
                    y=[item["h"] for item in curves["system"]],
                    mode="lines",
                    name="Характеристика трубопровода",
                    line={"color": "#2e9e6b", "width": 2.5, "dash": "dash"},
                )
            )
        if nominal["q"] and nominal["h"]:
            fig.add_trace(
                go.Scatter(
                    x=[nominal["q"]],
                    y=[nominal["h"]],
                    mode="markers+text",
                    text=["номинал"],
                    textposition="top center",
                    name="Номинал",
                    marker={"size": 13, "color": "#2f80ed", "symbol": "diamond"},
                )
            )
        h_due = curves["due"]["h"]
        if h_due:
            fig.add_trace(
                go.Scatter(
                    x=[q_work],
                    y=[h_due],
                    mode="markers",
                    name="Должный напор (29)",
                    marker={"size": 12, "color": "#e0a106"},
                )
            )
        fig.add_trace(
            go.Scatter(
                x=[q_work],
                y=[point["h"]],
                mode="markers+text",
                text=["раб. точка"],
                textposition="bottom center",
                name="Факт",
                marker={
                    "size": 16,
                    "color": "#d9534f",
                    "symbol": "x",
                    "line": {"width": 2, "color": "#9c2b27"},
                },
            )
        )
        fig.update_layout(
            title="Q–H: насос и трубопровод",
            xaxis_title="Q, м³/ч",
            yaxis_title="H, м",
            height=420,
            margin={"t": 46, "b": 10},
            legend={"orientation": "h", "y": -0.22},
            plot_bgcolor="#ffffff",
        )
        st.plotly_chart(fig, width="stretch")
    with cc[1]:
        fig = go.Figure()
        if curves["qeta"]:
            is_pass = curves["origin"]["qeta"] == "passport"
            fig.add_trace(
                go.Scatter(
                    x=[item["q"] for item in curves["qeta"]],
                    y=[item["eta"] for item in curves["qeta"]],
                    mode="lines",
                    name="Q-η · паспорт" if is_pass else "Q-η · модель",
                    line={"color": "#1f4e79", "width": 3, "dash": None if is_pass else "dot"},
                )
            )
        if nominal["q"] and nominal["eta"]:
            fig.add_trace(
                go.Scatter(
                    x=[nominal["q"]],
                    y=[nominal["eta"]],
                    mode="markers+text",
                    text=["номинал"],
                    textposition="top center",
                    name="Номинал",
                    marker={"size": 13, "color": "#2f80ed", "symbol": "diamond"},
                )
            )
        fig.add_trace(
            go.Scatter(
                x=[q_work],
                y=[point["eta"]],
                mode="markers+text",
                text=["факт"],
                textposition="bottom center",
                name="КПД факт",
                marker={
                    "size": 16,
                    "color": "#d9534f",
                    "symbol": "x",
                    "line": {"width": 2, "color": "#9c2b27"},
                },
            )
        )
        fig.update_layout(
            title="Q–η: КПД насоса",
            xaxis_title="Q, м³/ч",
            yaxis_title="η, о.е.",
            height=420,
            margin={"t": 46, "b": 10},
            legend={"orientation": "h", "y": -0.22},
            plot_bgcolor="#ffffff",
        )
        st.plotly_chart(fig, width="stretch")
    st.caption(
        f"Рабочая подача Q = {fmt(q_work, 2)} м³/ч · напор факт {fmt(point['h'], 1)} м · "
        f"КПД факт {fmt(point['eta'], 3)}. Пунктир — модельные кривые (нет паспортных координат)."
    )
