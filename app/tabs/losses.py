"""📉 Карта потерь — waterfall-декомпозиция мощности + таблица долей и ₽/год."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st
import ui

from tabs.common import Ctx, fmt, loss_components


_LOSS_GLOSSARY = {
    "Потери КПД": "Дополнительная мощность сверх паспортного КПД: фактический КПД ниже η_ном.",
    "Номинальные": (
        "Базовые потери даже при паспортном КПД: электрическая мощность, "
        "неизбежно теряемая в насосе, ЭД, трансмиссии и ПЧ."
    ),
    "Дросселирование": "Потери на снижении давления арматурой перед БГ.",
    "Гидравл. насос→БГ": (
        "Потеря давления от выкида НА до БГ: трубопровод, арматура и местные сопротивления."
    ),
    "Износ": "Оценка потерь из-за снижения КПД насоса относительно должного состояния.",
    "Неоптим. подача": "Потери из-за работы насоса вне расчётной оптимальной подачи.",
    "Завыш. мощность ЭД": (
        "Потери, отнесённые к фактической работе электродвигателя сверх расчётной модели."
    ),
    "Вязкость": "Потери из-за влияния вязкости жидкости на КПД насоса.",
}


def _loss_glossary(labels: list[str]) -> list[tuple[str, str]]:
    return [(label, _LOSS_GLOSSARY[label]) for label in labels if label in _LOSS_GLOSSARY]


def _power_flow(ctx: Ctx) -> None:
    st.markdown("**Поток мощности: P_эл → полезная мощность + статьи потерь**")
    useful, losses = loss_components(ctx.audit)
    losses = [(label, value) for label, value in losses if abs(value) > 1e-6]
    p_el = ctx.audit.regime.p_electric or 0.0
    node_labels = [f"P_эл  {fmt(p_el, 0)} кВт", f"Полезная  {fmt(useful, 0)}"] + [
        f"{label}  {fmt(value, 0)}" for label, value in losses
    ]
    node_colors = ["#2f80ed", "#2e9e6b"] + ["#e08a6b"] * len(losses)
    fig = go.Figure(
        go.Sankey(
            arrangement="snap",
            textfont={"color": "#13212e", "size": 14, "family": "sans-serif"},
            node={
                "label": node_labels,
                "color": node_colors,
                "pad": 26,
                "thickness": 22,
                "line": {"color": "#33495f", "width": 0.8},
            },
            link={
                "source": [0] * (1 + len(losses)),
                "target": list(range(1, 2 + len(losses))),
                "value": [max(useful, 1e-9)] + [max(value, 1e-9) for _, value in losses],
                "color": ["rgba(46,158,107,0.40)"]
                + ["rgba(224,138,107,0.38)"] * len(losses),
            },
        )
    )
    fig.update_layout(
        height=380,
        margin={"t": 14, "b": 14, "l": 10, "r": 10},
        font={"size": 14, "color": "#13212e"},
        paper_bgcolor="white",
    )
    st.plotly_chart(fig, width="stretch")
    pct_useful = useful / p_el * 100 if p_el else 0.0
    st.caption(
        f"P_эл = {fmt(p_el, 1)} кВт · полезная {fmt(useful, 1)} кВт "
        f"({fmt(pct_useful, 1)} %). Ширина потока пропорциональна доле мощности."
    )


def render(ctx: Ctx) -> None:
    st.subheader("Цифровая карта потерь мощности")
    if ctx.quality is not None and not ctx.quality.allows_economic_conclusions:
        st.warning(
            "Карта потерь не построена: выбранный режим непригоден для экономических выводов."
        )
        return
    audit, tariff = ctx.audit, ctx.tariff
    if ctx.source == "field_trip" and not ctx.scope.annual_runtime_is_assumed:
        ui.provenance((f"T_год из YAML: {fmt(ctx.scope.annual_runtime_hours, 1)} ч", "ok"))
    elif ctx.scope.annual_runtime_is_assumed:
        ui.provenance(("Сценарий: T_год = 8760 ч", "warn"))
        st.warning(
            "Годовые суммы — сценарий непрерывной работы: фактическая T_год не подтверждена."
        )
    else:
        ui.provenance((f"T_год из телеметрии: {fmt(ctx.scope.annual_runtime_hours, 1)} ч", "ok"))
    useful, losses = loss_components(audit)
    p_el = audit.regime.p_electric
    losses = [(lbl, v) for lbl, v in losses if abs(v) > 1e-6]

    if not losses:
        st.info(
            "Декомпозиция потерь по статьям (формулы 31–36 / 37–42) для этого агрегата "
            "неприменима: объёмный насос без p_БГ либо нет данных для декомпозиции. "
            "Ниже — полезная мощность против подведённой."
        )

    labels = ["P_эл (подвод)"] + [label for label, _ in losses] + ["Полезная мощность"]
    measures = ["absolute"] + ["relative"] * len(losses) + ["total"]
    values = [p_el] + [-v for _, v in losses] + [0]
    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=measures,
            x=labels,
            y=values,
            textposition="outside",
            text=[fmt(p_el, 1)] + [fmt(-v, 1) for _, v in losses] + [fmt(useful, 1)],
            connector={"line": {"color": "#bbb"}},
            decreasing={"marker": {"color": "#e07a5f"}},
            increasing={"marker": {"color": "#81b29a"}},
            totals={"marker": {"color": "#3d5a80"}},
        )
    )
    fig.update_layout(
        height=440, yaxis_title="кВт", margin={"t": 30, "b": 10}, font={"family": "sans-serif"}
    )
    st.plotly_chart(fig, width="stretch")
    _power_flow(ctx)

    st.markdown("**Структура (доли от подведённой мощности P_эл):**")
    t_year = ctx.scope.annual_runtime_hours
    rows = [("Полезная мощность", useful)] + losses
    st.dataframe(
        {
            "Составляющая": [r[0] for r in rows],
            "кВт": [fmt(r[1], 2) for r in rows],
            "% от P_эл": [fmt(r[1] / p_el * 100, 1) for r in rows],
            "тыс. ₽/год": [fmt(r[1] * t_year * tariff / 1000, 0) for r in rows],
        },
        width="stretch",
        hide_index=True,
    )
    glossary = _loss_glossary([label for label, _ in losses])
    if glossary:
        st.markdown("### Расшифровка статей")
        st.dataframe(
            {
                "Статья": [label for label, _ in glossary],
                "Что означает": [meaning for _, meaning in glossary],
            },
            width="stretch",
            hide_index=True,
        )
    qualifier = (
        "сценарий"
        if ctx.scope.annual_runtime_is_assumed
        else "выездная оценка" if ctx.source == "field_trip" else "оценка по телеметрии"
    )
    st.caption(f"₽/год — {qualifier}: T_год {fmt(t_year, 0)} ч, тариф {fmt(tariff, 2)} ₽/кВт·ч.")
