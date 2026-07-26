"""📋 Обзор — главный экран: за 30 секунд отвечает руководителю.

Сверху вниз: KPI (УРЭ факт/расчёт/оптимум, КПД, потери в кВт·ч и ₽) → структура
потерь + топ-мероприятия с эффектом → gauge КПД и бар УРЭ → паспорт и режим →
выдержка из текстового отчёта.
"""

from __future__ import annotations

import lib
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import ui

from tabs.common import Ctx, fmt, loss_components


def _kpi_rows(ctx: Ctx) -> None:
    audit, reg = ctx.audit, ctx.audit.regime
    if not ctx.scope.daily_pressure_coverage_is_complete:
        ui.provenance(
            ("Режимный расчёт: снимок давления", "warn"),
            ("Суточный УРЭ: W / Q_сут", "ok"),
        )
    elif ctx.scope.daily_kpi_is_fact:
        ui.provenance(("Суточный факт: W / Q_сут", "ok"), ("Расчёт по Методике", ""))
    else:
        ui.provenance(("УРЭ по режиму, не суточный факт", "warn"), ("Расчёт по Методике", ""))
    c = st.columns(4)
    sec_dev = (audit.sec_fact - audit.sec_calc) / audit.sec_calc * 100 if audit.sec_calc else None
    c[0].metric(
        "УРЭ факт, кВт·ч/м³",
        fmt(audit.sec_fact, 3),
        f"{fmt(sec_dev, 1)} % к расчётному" if sec_dev is not None else None,
        delta_color="inverse",
        help="Фактический удельный расход ЭЭ = W / Q_сут (формула 16).",
    )
    c[1].metric(
        "УРЭ расчётный, кВт·ч/м³",
        fmt(audit.sec_calc, 3),
        help="По напору и номинальному КПД (формула 17). Разница с фактом = потери КПД.",
    )
    c[2].metric(
        "УРЭ оптимальный, кВт·ч/м³",
        fmt(audit.sec_optimal, 3),
        help="По оптимальному давлению (формула 18); для КНС p_опт = p_БГ. "
        "«—» — нет p_БГ (ветка перекачки) или реестра НДТ.",
    )
    c[3].metric(
        "Цель ППД-2035",
        fmt(lib.constraints().kpi.get("target_sec_2035"), 2),
        help="Целевой УРЭ системы ППД к 2035 г. (ТЗ).",
    )

    c = st.columns(2)
    c[0].metric(
        "КПД факт",
        fmt(reg.eta_unit, 3),
        help="Фактический КПД насосной установки = P_гидр / P_эл (формула 13).",
    )
    c[1].metric(
        "КПД номинальный",
        fmt(reg.eta_nom, 3),
        help="Паспортный КПД (η_ЭД·η_нас·η_тр, формула 14/15).",
    )


def _annual_kpis(ctx: Ctx) -> None:
    audit, tariff = ctx.audit, ctx.tariff
    if ctx.scope.annual_runtime_is_assumed:
        ui.provenance(("Сценарий: T_год = 8760 ч", "warn"), ("Тариф и цель — конфиг", ""))
        st.warning("Годовые значения не являются фактом: нет полного года ежедневных моточасов.")
    else:
        ui.provenance(
            (f"Год телеметрии: T_год = {fmt(ctx.scope.annual_runtime_hours, 1)} ч", "ok"),
            ("Тариф и цель — конфиг", ""),
        )
    c = st.columns(2)
    c[0].metric(
        "ΔW по КПД, кВт·ч/год",
        fmt(audit.dw_efficiency, 0),
        help="Годовые потери из-за снижения КПД (формула 44).",
    )
    c[1].metric(
        "ΔW по КПД, тыс. ₽/год",
        fmt(audit.dw_efficiency * tariff / 1000, 1),
        help="Те же потери в деньгах по тарифу.",
    )


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
                (lbl, v, c)
                for (lbl, v), c in zip(
                    losses, ["#d9534f", "#e0a106", "#e08a6b", "#c48a4a", "#9aa5b1"], strict=False
                )
            ]
            fig = go.Figure()
            for lbl, v, color in parts:
                fig.add_trace(
                    go.Bar(
                        x=[v / p_el * 100],
                        y=[""],
                        orientation="h",
                        name=lbl,
                        marker_color=color,
                        text=f"{lbl}<br>{v / p_el * 100:.0f} %",
                        textposition="inside",
                        hovertemplate=(
                            f"{lbl}: {fmt(v, 1)} кВт ({v / p_el * 100:.1f} %)<extra></extra>"
                        ),
                    )
                )
            fig.update_layout(
                barmode="stack",
                height=110,
                showlegend=False,
                margin={"t": 6, "b": 6, "l": 6, "r": 6},
                xaxis={"title": "% от P_эл", "range": [0, 100]},
                yaxis={"visible": False},
                plot_bgcolor="white",
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            if not losses:
                st.caption(
                    "Для объёмного насоса декомпозиция потерь (37–42) неприменима — "
                    "показана полезная гидравлическая мощность. Детали — вкладка «Карта потерь»."
                )
            else:
                st.caption("Детализация по статьям и ₽/год — вкладка «📉 Карта потерь».")
    with cc[1]:
        st.markdown("**Топ-мероприятия** — что даст наибольший эффект")
        ui.provenance(("Эвристическая оценка", "warn"))
        evals = suggest_measures(audit, tariff)[:3]
        if not evals:
            st.info(
                "В текущем каталоге нет применимого мероприятия. "
                "Это не означает, что потери в норме."
            )
        else:
            st.dataframe(
                pd.DataFrame([
                    {
                        "Мероприятие": e.name,
                        "кВт·ч/год": fmt(e.energy_saving_kwh, 0),
                        "тыс. ₽/год": fmt(e.money_saving_krub, 1),
                        "Окуп., лет": (
                            "требует оценки"
                            if e.cls == "сценарная оценка"
                            else fmt(e.payback_years, 1) if e.payback_years else "без CAPEX"
                        ),
                    }
                    for e in evals
                ]),
                width="stretch",
                hide_index=True,
            )
            st.caption("Полный реестр с ТЭО — вкладка «💡 Мероприятия».")


def _gauge_and_sec_bar(ctx: Ctx) -> None:
    audit, reg = ctx.audit, ctx.audit.regime
    gc = st.columns([1, 1.4])
    with gc[0]:
        en = reg.eta_nom or 0.7
        gfig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=reg.eta_unit,
                number={"valueformat": ".3f"},
                title={"text": "КПД установки (факт)", "font": {"size": 14}},
                gauge={
                    "axis": {"range": [0, max(en, reg.eta_unit) * 1.15]},
                    "bar": {"color": "#2f80ed"},
                    "steps": [
                        {"range": [0, en * 0.78], "color": "#f6d6d2"},
                        {"range": [en * 0.78, en * 0.9], "color": "#fdeecb"},
                        {"range": [en * 0.9, max(en, reg.eta_unit) * 1.15], "color": "#cdeedd"},
                    ],
                    "threshold": {"line": {"color": "#1f4e79", "width": 4}, "value": en},
                },
            )
        )
        gfig.update_layout(height=250, margin={"t": 40, "b": 10, "l": 24, "r": 24})
        st.plotly_chart(gfig, width="stretch")
        st.caption(
            "Порог (синяя черта) — номинальный КПД. Зоны: 🔴 <0,78·ном · 🟡 <0,9·ном · 🟢 норма."
        )
    with gc[1]:
        labels = ["факт", "расчётный", "оптимальный", "цель-2035"]
        vals = [
            audit.sec_fact,
            audit.sec_calc,
            audit.sec_optimal,
            lib.constraints().kpi.get("target_sec_2035"),
        ]
        bfig = go.Figure(
            go.Bar(
                x=labels,
                y=vals,
                marker_color=["#d9534f", "#2f80ed", "#2e9e6b", "#1f4e79"],
                text=[fmt(v, 2) for v in vals],
                textposition="outside",
                textfont={"size": 13},
            )
        )
        bfig.update_layout(
            height=250,
            margin={"t": 40, "b": 10},
            yaxis_title="кВт·ч/м³",
            title={"text": "УРЭ: факт → расчёт → оптимум → цель", "font": {"size": 14}},
            plot_bgcolor="#f7fafd",
        )
        st.plotly_chart(bfig, width="stretch")


def _passport_and_regime(ctx: Ctx) -> None:
    p, m, rm = ctx.agg.pump, ctx.agg.motor, ctx.agg.regime
    st.subheader("Паспорт и режим")
    col1, col2 = st.columns(2)

    def table(title: str, rows: dict) -> None:
        st.markdown(f"**{title}**")
        st.dataframe(
            pd.DataFrame([
                {
                    "Параметр": k,
                    "Значение": (v if isinstance(v, str) else fmt(v, 3)) if v is not None else "—",
                }
                for k, v in rows.items()
            ]),
            width="stretch",
            hide_index=True,
        )

    with col1:
        table(
            "Насос",
            {
                "Модель": p.model or "—",
                "Тип": p.kind.value,
                "Q_ном, м³/ч": p.q_nom,
                "H_ном, м": p.h_nom,
                "η_нас.ном, о.е.": p.eta_nom,
                "n, об/мин": p.n_rpm,
            },
        )
    with col2:
        table(
            "Электродвигатель",
            {
                "Модель": m.model or "—",
                "Тип": "синхронный" if m.synchronous else "асинхронный",
                "P_ном, кВт": m.p_nom,
                "η_ЭД.ном, о.е.": m.eta_nom,
                "cos φ": m.cos_phi,
                "U, кВ": m.voltage_kv,
            },
        )
    col1, col2 = st.columns(2)
    with col1:
        table(
            "Режимный снимок",
            {
                "Время снимка": ctx.snapshot_timestamp.strftime("%d.%m.%Y %H:%M:%S"),
                "p_вх, МПа": rm.p_in,
                "p_вых, МПа": rm.p_out,
                "p_БГ, МПа": rm.p_bg,
                "Δp, МПа": rm.p_out - rm.p_in,
            },
        )
    with col2:
        table(
            "Суточные данные",
            {
                "ρ, кг/м³": rm.rho,
                "Q_сут, м³": rm.q_day,
                "Моточасы, ч": rm.t,
                "W, кВт·ч": rm.w,
                "P_эл средняя, кВт": rm.p_electric,
                "T_год, ч": rm.t_year,
            },
        )


def _report_excerpt(ctx: Ctx) -> None:
    facts = lib.get_report_facts(ctx.object_id)
    if not facts:
        return
    src = facts["source"].split("/")[-1]
    with st.expander(f"📄 Текстовый отчёт энергоаудита — выводы (источник: {src})"):
        ui.provenance(("Из текстового отчёта", ""))
        ra = facts.get("aggregates", {}).get(ctx.agg_id, {})
        for c in ra.get("claims", []):
            st.markdown(f"> {c['text']}")
        teo = facts.get("teo", {})
        if teo.get("headline"):
            st.info("ТЭО: " + teo["headline"])
        elif teo.get("total_loss_kwh"):
            st.caption(
                f"Годовые потери по отчёту: {fmt(teo['total_loss_kwh'], 0)} кВт·ч"
                + (
                    f" · {fmt(teo.get('total_loss_krub'), 1)} тыс. ₽"
                    if teo.get("total_loss_krub")
                    else ""
                )
            )
        if facts.get("recommendations"):
            st.markdown("**Рекомендации отчёта:**")
            for rrec in facts["recommendations"][:5]:
                st.markdown(f"- {rrec}")


def render(ctx: Ctx) -> None:
    st.subheader("Суточный KPI")
    _kpi_rows(ctx)
    st.divider()
    st.subheader("Режимный расчёт")
    _loss_structure_and_measures(ctx)
    st.divider()
    _gauge_and_sec_bar(ctx)
    st.divider()
    st.subheader("Годовая оценка")
    _annual_kpis(ctx)
    st.divider()
    _passport_and_regime(ctx)
    _report_excerpt(ctx)
