"""📋 Обзор — главный экран: за 30 секунд отвечает руководителю.

Сверху вниз: KPI (УРЭ факт/расчёт/оптимум, КПД, потери в кВт·ч и ₽) → структура
потерь + топ-мероприятия с эффектом → gauge КПД и бар УРЭ → паспорт и режим.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import lib
from tabs.common import Ctx, fmt, loss_components


def _kpi_rows(ctx: Ctx) -> None:
    audit, reg, tariff = ctx.audit, ctx.audit.regime, ctx.tariff
    c = st.columns(4)
    sec_dev = (audit.sec_fact - audit.sec_calc) / audit.sec_calc * 100 if audit.sec_calc else None
    c[0].metric("УРЭ факт, кВт·ч/м³", fmt(audit.sec_fact, 3),
                f"{fmt(sec_dev,1)} % к расчётному" if sec_dev is not None else None,
                delta_color="inverse",
                help="Фактический удельный расход ЭЭ = W / Q_сут (формула 16).")
    c[1].metric("УРЭ расчётный, кВт·ч/м³", fmt(audit.sec_calc, 3),
                help="По напору и номинальному КПД (формула 17). Разница с фактом = потери КПД.")
    c[2].metric("УРЭ оптимальный, кВт·ч/м³", fmt(audit.sec_optimal, 3),
                help="По оптимальному давлению (формула 18); для КНС p_опт = p_БГ. "
                     "«—» — нет p_БГ (ветка перекачки) или реестра НДТ.")
    c[3].metric("Цель ППД-2035", fmt(lib.constraints().kpi.get("target_sec_2035"), 2),
                help="Целевой УРЭ системы ППД к 2035 г. (ТЗ).")

    c = st.columns(4)
    c[0].metric("КПД факт", fmt(reg.eta_unit, 3),
                help="Фактический КПД насосной установки = P_гидр / P_эл (формула 13).")
    c[1].metric("КПД номинальный", fmt(reg.eta_nom, 3),
                help="Паспортный КПД (η_ЭД·η_нас·η_тр, формула 14/15).")
    c[2].metric("ΔW по КПД, кВт·ч/год", fmt(audit.dw_efficiency, 0),
                help="Годовые потери из-за снижения КПД (формула 44).")
    c[3].metric("ΔW по КПД, тыс. ₽/год", fmt(audit.dw_efficiency * tariff / 1000, 1),
                help="Те же потери в деньгах по тарифу.")


def _loss_structure_and_measures(ctx: Ctx) -> None:
    """Структура потерь (стек-полоса долей P_эл) + топ-мероприятия с эффектом."""
    from ppd_audit.measures import suggest_measures

    audit, tariff = ctx.audit, ctx.tariff
    useful, losses = loss_components(audit)
    losses = [(lbl, v) for lbl, v in losses if abs(v) > 1e-6]
    p_el = audit.regime.p_electric or 0.0

    cc = st.columns([1.25, 1])
    with cc[0]:
        st.markdown("**Структура потерь** — куда уходит подведённая мощность")
        if p_el <= 0:
            st.info("Нет данных об электрической мощности.")
        else:
            parts = [("Полезная", useful, "#2e9e6b")] + [
                (lbl, v, c) for (lbl, v), c in zip(
                    losses, ["#d9534f", "#e0a106", "#e08a6b", "#c48a4a", "#9aa5b1"])]
            fig = go.Figure()
            for lbl, v, color in parts:
                fig.add_trace(go.Bar(
                    x=[v / p_el * 100], y=[""], orientation="h", name=lbl,
                    marker_color=color,
                    text=f"{lbl}<br>{v / p_el * 100:.0f} %", textposition="inside",
                    hovertemplate=f"{lbl}: {fmt(v, 1)} кВт ({v / p_el * 100:.1f} %)<extra></extra>"))
            fig.update_layout(barmode="stack", height=110, showlegend=False,
                              margin=dict(t=6, b=6, l=6, r=6),
                              xaxis=dict(title="% от P_эл", range=[0, 100]),
                              yaxis=dict(visible=False), plot_bgcolor="white")
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            if not losses:
                st.caption("Для объёмного насоса декомпозиция потерь (37–42) неприменима — "
                           "показана полезная гидравлическая мощность. Детали — вкладка «Карта потерь».")
            else:
                st.caption("Детализация по статьям и ₽/год — вкладка «📉 Карта потерь».")
    with cc[1]:
        st.markdown("**Топ-мероприятия** — что даст наибольший эффект")
        evals = suggest_measures(audit, tariff)[:3]
        if not evals:
            st.success("Применимых мероприятий не выявлено — режим близок к норме.")
        else:
            st.dataframe(pd.DataFrame([{
                "Мероприятие": e.name,
                "кВт·ч/год": fmt(e.energy_saving_kwh, 0),
                "тыс. ₽/год": fmt(e.money_saving_krub, 1),
                "Окуп., лет": fmt(e.payback_years, 1) if e.payback_years else "без CAPEX",
            } for e in evals]), width="stretch", hide_index=True)
            st.caption("Полный реестр с ТЭО — вкладка «💡 Мероприятия».")


def _gauge_and_sec_bar(ctx: Ctx) -> None:
    audit, reg = ctx.audit, ctx.audit.regime
    gc = st.columns([1, 1.4])
    with gc[0]:
        en = reg.eta_nom or 0.7
        gfig = go.Figure(go.Indicator(
            mode="gauge+number", value=reg.eta_unit, number={"valueformat": ".3f"},
            title={"text": "КПД установки (факт)", "font": {"size": 14}},
            gauge={"axis": {"range": [0, max(en, reg.eta_unit) * 1.15]},
                   "bar": {"color": "#2f80ed"},
                   "steps": [{"range": [0, en * 0.78], "color": "#f6d6d2"},
                             {"range": [en * 0.78, en * 0.9], "color": "#fdeecb"},
                             {"range": [en * 0.9, max(en, reg.eta_unit) * 1.15], "color": "#cdeedd"}],
                   "threshold": {"line": {"color": "#1f4e79", "width": 4}, "value": en}}))
        gfig.update_layout(height=250, margin=dict(t=40, b=10, l=24, r=24))
        st.plotly_chart(gfig, width="stretch")
        st.caption("Порог (синяя черта) — номинальный КПД. Зоны: 🔴 <0,78·ном · 🟡 <0,9·ном · 🟢 норма.")
    with gc[1]:
        labels = ["факт", "расчётный", "оптимальный", "цель-2035"]
        vals = [audit.sec_fact, audit.sec_calc, audit.sec_optimal,
                lib.constraints().kpi.get("target_sec_2035")]
        bfig = go.Figure(go.Bar(x=labels, y=vals,
                                marker_color=["#d9534f", "#2f80ed", "#2e9e6b", "#1f4e79"],
                                text=[fmt(v, 2) for v in vals], textposition="outside",
                                textfont=dict(size=13)))
        bfig.update_layout(height=250, margin=dict(t=40, b=10), yaxis_title="кВт·ч/м³",
                           title={"text": "УРЭ: факт → расчёт → оптимум → цель", "font": {"size": 14}},
                           plot_bgcolor="#f7fafd")
        st.plotly_chart(bfig, width="stretch")


def _passport_and_regime(ctx: Ctx) -> None:
    p, m, rm = ctx.agg.pump, ctx.agg.motor, ctx.agg.regime
    st.subheader("Паспорт и режим")
    col1, col2, col3 = st.columns(3)

    def table(title: str, rows: dict) -> None:
        st.markdown(f"**{title}**")
        st.dataframe(pd.DataFrame(
            [{"Параметр": k, "Значение": (v if isinstance(v, str) else fmt(v, 3))
              if v is not None else "—"} for k, v in rows.items()]),
            width="stretch", hide_index=True)

    with col1:
        table("Насос", {"Модель": p.model or "—", "Тип": p.kind.value,
                        "Q_ном, м³/ч": p.q_nom, "H_ном, м": p.h_nom,
                        "η_нас.ном, о.е.": p.eta_nom, "n, об/мин": p.n_rpm})
    with col2:
        table("Электродвигатель", {
            "Модель": m.model or "—",
            "Тип": "синхронный" if m.synchronous else "асинхронный",
            "P_ном, кВт": m.p_nom, "η_ЭД.ном, о.е.": m.eta_nom,
            "cos φ": m.cos_phi, "U, кВ": m.voltage_kv})
    with col3:
        table("Режим (замер)", {
            "ρ, кг/м³": rm.rho, "p_вх, МПа": rm.p_in, "p_вых, МПа": rm.p_out,
            "p_БГ, МПа": rm.p_bg, "Q_сут, м³": rm.q_day, "T, ч/сут": rm.t,
            "W, кВт·ч/сут": rm.w, "T_год, ч": rm.t_year})


def render(ctx: Ctx) -> None:
    st.subheader("Ключевые показатели (KPI)")
    _kpi_rows(ctx)
    st.divider()
    _loss_structure_and_measures(ctx)
    st.divider()
    _gauge_and_sec_bar(ctx)
    st.divider()
    _passport_and_regime(ctx)
