"""📉 Карта потерь — waterfall-декомпозиция мощности + таблица долей и ₽/год."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from tabs.common import Ctx, fmt, loss_components


def render(ctx: Ctx) -> None:
    st.subheader("Цифровая карта потерь мощности")
    audit, agg, tariff = ctx.audit, ctx.agg, ctx.tariff
    useful, losses = loss_components(audit)
    p_el = audit.regime.p_electric
    losses = [(lbl, v) for lbl, v in losses if abs(v) > 1e-6]

    if not losses:
        st.info("Декомпозиция потерь по статьям (формулы 31–36 / 37–42) для этого агрегата "
                "неприменима: объёмный насос без p_БГ либо нет данных для декомпозиции. "
                "Ниже — полезная мощность против подведённой.")

    labels = ["P_эл (подвод)"] + [l for l, _ in losses] + ["Полезная мощность"]
    measures = ["absolute"] + ["relative"] * len(losses) + ["total"]
    values = [p_el] + [-v for _, v in losses] + [0]
    fig = go.Figure(go.Waterfall(
        orientation="v", measure=measures, x=labels, y=values,
        textposition="outside",
        text=[fmt(p_el, 1)] + [fmt(-v, 1) for _, v in losses] + [fmt(useful, 1)],
        connector={"line": {"color": "#bbb"}},
        decreasing={"marker": {"color": "#e07a5f"}},
        increasing={"marker": {"color": "#81b29a"}},
        totals={"marker": {"color": "#3d5a80"}}))
    fig.update_layout(height=440, yaxis_title="кВт", margin=dict(t=30, b=10),
                      font=dict(family="sans-serif"))
    st.plotly_chart(fig, width="stretch")

    st.markdown("**Структура (доли от подведённой мощности P_эл):**")
    t_year = agg.regime.t_year or 8760
    rows = [("Полезная мощность", useful)] + losses
    st.dataframe(
        {"Составляющая": [r[0] for r in rows],
         "кВт": [fmt(r[1], 2) for r in rows],
         "% от P_эл": [fmt(r[1] / p_el * 100, 1) for r in rows],
         "тыс. ₽/год": [fmt(r[1] * t_year * tariff / 1000, 0) for r in rows]},
        width="stretch", hide_index=True)
    st.caption(f"₽/год — по годовой наработке {fmt(t_year,0)} ч и тарифу {fmt(tariff,2)} ₽/кВт·ч.")
