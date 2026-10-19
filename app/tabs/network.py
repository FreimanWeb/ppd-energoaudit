"""Водоводы и скважины: потери давления от блок-гребёнки до устья скважин."""

from __future__ import annotations

import lib
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import ui

from tabs.common import Ctx, fmt


TOP_WELLS = 15
TOP_PIPELINES = 15
_PARTS = (
    ("friction_kw", "Трение в водоводах", ui.PALETTE["water_dark"]),
    ("other_kw", "Задвижки и прочие", ui.PALETTE["muted"]),
    ("choke_kw", "Штуцеры", ui.PALETTE["throttle"]),
)


def _audit_eta(ctx: Ctx) -> float | None:
    """КПД насосной установки выбранного режима, если он пригоден для выводов."""
    quality = ctx.quality
    if quality is not None and not quality.allows_economic_conclusions:
        return None
    eta = getattr(getattr(ctx.audit, "regime", None), "eta_unit", None)
    return eta if eta and 0 < eta <= 1 else None


def _source_line(view: dict) -> str:
    source = view["p_bg_source"]
    pressure = (
        f"p_БГ по телеметрии {source['start']} — {source['end']}"
        if source["kind"] == "telemetry"
        else "p_БГ по карточкам скважин"
    )
    eta = "КПД выбранного режима" if view["eta_basis"] == "fact" else "номинальный КПД станции"
    return (
        f"Скважины: {view['month'] or '—'} · {pressure} · ρ {fmt(view['fluid']['rho'], 0)} кг/м³ · "
        f"{eta} {fmt(view['eta'], 3)} · тариф {fmt(view['tariff'], 2)} ₽/кВт·ч"
    )


def _metrics(view: dict) -> None:
    totals = view["totals"]
    columns = st.columns(4)
    columns[0].metric("Давление на БГ, МПа", fmt(view["p_bg_mpa"], 2))
    columns[1].metric("Закачка, м³/ч", fmt(totals["q_m3h"], 1))
    columns[2].metric(
        "Потери в сети, кВт",
        fmt(totals["friction_kw"] + totals["other_kw"] + totals["choke_kw"], 1),
    )
    columns[3].metric("Годовые потери, тыс. ₽", fmt(totals["money_krub"], 0))
    parts = st.columns(4)
    parts[0].metric("Трение, тыс. кВт·ч/год", fmt(totals["friction_kwh"] / 1000, 0))
    parts[1].metric("Задвижки и прочие, тыс. кВт·ч/год", fmt(totals["other_kwh"] / 1000, 0))
    parts[2].metric("Штуцеры, тыс. кВт·ч/год", fmt(totals["choke_kwh"] / 1000, 0))
    if totals["excess_pressure_mpa"]:
        parts[3].metric("Избыток давления на БГ, МПа", fmt(totals["excess_pressure_mpa"], 2))


def _chart(wells: list[dict]) -> None:
    top = sorted(wells, key=lambda well: well["loss_kw"], reverse=True)[:TOP_WELLS]
    top = [well for well in top if well["loss_kw"] > 0][::-1]
    if not top:
        return
    fig = go.Figure([
        go.Bar(
            y=[well["well"] for well in top],
            x=[well[key] for well in top],
            name=label,
            orientation="h",
            marker_color=color,
            hovertemplate="Скв. %{y}: %{x:.1f} кВт<extra>" + label + "</extra>",
        )
        for key, label, color in _PARTS
    ])
    fig.update_layout(
        barmode="stack",
        height=max(260, 26 * len(top) + 90),
        margin={"l": 70, "r": 20, "t": 10, "b": 40},
        xaxis_title="Мощность потерь, кВт",
        yaxis={"type": "category"},
        legend={"orientation": "h", "y": -0.18},
        plot_bgcolor="#ffffff",
    )
    st.plotly_chart(fig, use_container_width=True)


def _wells_table(wells: list[dict]) -> None:
    rows = [
        {
            "Скважина": well["well"],
            "Q, м³/ч": well["q_m3h"],
            "Путь, м": well["path_length_m"] or None,
            "p после шт., МПа": well["p_after_choke_mpa"],
            "Трение, МПа": well["dp_friction_mpa"],
            "Задвижки и прочие, МПа": well["dp_other_mpa"],
            "Штуцер, МПа": well["dp_choke_mpa"],
            "Потери, кВт": well["loss_kw"],
            "Потери, тыс. кВт·ч/год": well["annual_kwh"] / 1000,
            "Примечание": "; ".join(well["flags"]),
        }
        for well in wells
    ]
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Q, м³/ч": st.column_config.NumberColumn(format="%.2f"),
            "Путь, м": st.column_config.NumberColumn(format="%.0f"),
            "p после шт., МПа": st.column_config.NumberColumn(format="%.2f"),
            "Трение, МПа": st.column_config.NumberColumn(format="%.2f"),
            "Задвижки и прочие, МПа": st.column_config.NumberColumn(format="%.2f"),
            "Штуцер, МПа": st.column_config.NumberColumn(format="%.2f"),
            "Потери, кВт": st.column_config.NumberColumn(format="%.1f"),
            "Потери, тыс. кВт·ч/год": st.column_config.NumberColumn(format="%.0f"),
        },
    )


def _pipelines_table(pipelines: list[dict]) -> None:
    rows = [
        {
            "Водовод": pipe["name"],
            "Длина, м": pipe["length_m"],
            "D×s, мм": pipe["sizes"],
            "Тип трубы": pipe["pipe_types"],
            "Q, м³/ч": pipe["q_m3h"],
            "Скорость, м/с": pipe["velocity_ms"],
            "Трение, МПа": pipe["dp_friction_mpa"],
        }
        for pipe in pipelines[:TOP_PIPELINES]
    ]
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Длина, м": st.column_config.NumberColumn(format="%.0f"),
            "Q, м³/ч": st.column_config.NumberColumn(format="%.1f"),
            "Скорость, м/с": st.column_config.NumberColumn(format="%.2f"),
            "Трение, МПа": st.column_config.NumberColumn(format="%.2f"),
        },
    )


def render(ctx: Ctx) -> None:
    st.subheader("Водоводы и скважины")
    view = lib.network(ctx.object_id, _audit_eta(ctx))
    if "error" in view:
        st.info(view["error"])
        return
    st.caption(_source_line(view))
    _metrics(view)
    st.markdown("**Потери мощности по скважинам**")
    _chart(view["wells"])
    st.markdown("**Скважины**")
    _wells_table(view["wells"])
    st.markdown("**Водоводы с наибольшим трением**")
    _pipelines_table(view["pipelines"])
