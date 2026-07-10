"""📈 Рабочая точка — Q-H (насос × трубопровод) и Q-η с фактической точкой."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import ui
from tabs.common import Ctx, fmt


def _pump_qh_curve(p):
    """Q-H: паспортная кривая или модельная парабола (центробежный). → (qs, hs, паспорт?) | None."""
    if p.curve_qh:
        return [c[0] for c in p.curve_qh], [c[1] for c in p.curve_qh], True
    if p.kind.value == "объёмный" or not (p.q_nom and p.h_nom):
        return None
    h0 = 1.22 * p.h_nom                       # напор при закрытой задвижке ~1,22·H_ном
    a = (h0 - p.h_nom) / (p.q_nom ** 2)
    qs = np.linspace(0, 1.5 * p.q_nom, 41)
    return qs, h0 - a * qs ** 2, False


def _system_curve(q_work, h_fact, p_in, p_bg, rho, q_nom):
    """Характеристика трубопровода H = H_ст + k·Q², проходящая через рабочую точку."""
    if not q_work or h_fact is None:
        return None
    h_st = ((p_bg - p_in) * 1e6 / (rho * 9.81)) if (p_bg and p_bg > p_in) else 0.35 * h_fact
    h_st = max(0.0, min(h_st, 0.95 * h_fact))
    k = (h_fact - h_st) / (q_work ** 2)
    qs = np.linspace(0, 1.5 * (q_nom or q_work), 41)
    return qs, h_st + k * qs ** 2


def render(ctx: Ctx) -> None:
    st.subheader("Рабочая точка: насос × трубопровод")
    p, audit = ctx.agg.pump, ctx.audit
    reg = audit.regime
    rmp = ctx.agg.regime
    q_work = rmp.flow()
    volumetric = p.kind.value == "объёмный"
    if volumetric:
        ui.note("Насос объёмного действия (плунжерный): паспортная кривая Q-H неприменима — "
                "подача задаётся числом ходов. Показаны фактические точки.")

    cc = st.columns(2)
    with cc[0]:
        fig = go.Figure()
        pc = _pump_qh_curve(p)
        if pc:
            qs, hs, is_pass = pc
            fig.add_trace(go.Scatter(x=qs, y=hs, mode="lines",
                          name="Кривая насоса · паспорт" if is_pass else "Кривая насоса · модель",
                          line=dict(color="#1f4e79", width=3, dash=None if is_pass else "dot")))
        sc = _system_curve(q_work, reg.h_fact, rmp.p_in, rmp.p_bg, rmp.rho, p.q_nom)
        if sc and not volumetric:
            fig.add_trace(go.Scatter(x=sc[0], y=sc[1], mode="lines",
                          name="Характеристика трубопровода",
                          line=dict(color="#2e9e6b", width=2.5, dash="dash")))
        if p.q_nom and p.h_nom and not volumetric:
            fig.add_trace(go.Scatter(x=[p.q_nom], y=[p.h_nom], mode="markers+text",
                          text=["номинал"], textposition="top center", name="Номинал",
                          marker=dict(size=13, color="#2f80ed", symbol="diamond")))
        h_due = audit.h_due or (audit.spec.reference.h_due if audit.spec.reference else None)
        if h_due:
            fig.add_trace(go.Scatter(x=[q_work], y=[h_due], mode="markers",
                          name="Должный напор (29)", marker=dict(size=12, color="#e0a106")))
        fig.add_trace(go.Scatter(x=[q_work], y=[reg.h_fact], mode="markers+text",
                      text=["раб. точка"], textposition="bottom center", name="Факт",
                      marker=dict(size=16, color="#d9534f", symbol="x",
                                  line=dict(width=2, color="#9c2b27"))))
        fig.update_layout(title="Q–H: насос и трубопровод", xaxis_title="Q, м³/ч",
                          yaxis_title="H, м", height=420, margin=dict(t=46, b=10),
                          legend=dict(orientation="h", y=-0.22), plot_bgcolor="#f7fafd")
        st.plotly_chart(fig, width="stretch")
    with cc[1]:
        fig = go.Figure()
        if p.curve_qeta:
            fig.add_trace(go.Scatter(x=[c[0] for c in p.curve_qeta],
                          y=[c[1] for c in p.curve_qeta],
                          mode="lines", name="Q-η · паспорт", line=dict(color="#1f4e79", width=3)))
        elif p.q_nom and p.eta_nom and not volumetric:
            qe = np.linspace(0.2 * p.q_nom, 1.4 * p.q_nom, 31)
            fig.add_trace(go.Scatter(x=qe, y=p.eta_nom * (1 - 0.9 * ((qe - p.q_nom) / p.q_nom) ** 2),
                          mode="lines", name="Q-η · модель",
                          line=dict(color="#1f4e79", width=3, dash="dot")))
        if p.q_nom and p.eta_nom and not volumetric:
            fig.add_trace(go.Scatter(x=[p.q_nom], y=[p.eta_nom], mode="markers+text",
                          text=["номинал"], textposition="top center", name="Номинал",
                          marker=dict(size=13, color="#2f80ed", symbol="diamond")))
        fig.add_trace(go.Scatter(x=[q_work], y=[reg.eta_unit], mode="markers+text",
                      text=["факт"], textposition="bottom center", name="КПД факт",
                      marker=dict(size=16, color="#d9534f", symbol="x",
                                  line=dict(width=2, color="#9c2b27"))))
        fig.update_layout(title="Q–η: КПД насоса", xaxis_title="Q, м³/ч", yaxis_title="η, о.е.",
                          height=420, margin=dict(t=46, b=10),
                          legend=dict(orientation="h", y=-0.22), plot_bgcolor="#f7fafd")
        st.plotly_chart(fig, width="stretch")
    st.caption(f"Рабочая подача Q = {fmt(q_work,2)} м³/ч · напор факт {fmt(reg.h_fact,1)} м · "
               f"КПД факт {fmt(reg.eta_unit,3)}. Пунктир — модельные кривые (нет паспортных координат).")
