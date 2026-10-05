"""Прогноз закачки — статистическая экстраполяция тренда на будущие периоды.

Использует суточные объёмы закачки/перекачки (метрика ``q_day`` из телеметрии,
см. ``services/telemetry_series.py``) и трендовую экстраполяцию из
``core/reservoir/forecast.py``. Это НЕ гидродинамическая модель пласта —
явно показываем это прямо на вкладке, а не только в докстринге ядра.
"""

from __future__ import annotations

import altair as alt
import lib
import pandas as pd
import streamlit as st
import ui

from ppd_audit.services.forecast_data import InsufficientForecastData
from tabs.common import Ctx, fmt


PERIOD_LABELS = {1: "сутки", 7: "неделя", 30: "месяц"}


def render(ctx: Ctx) -> None:
    st.subheader("Прогноз объёма закачки")
    st.caption("Экстраполяция тренда по факту — ориентир, не проектный расчёт.")

    all_dates = lib.telemetry_dates(ctx.object_id, ctx.agg_id)
    if len(all_dates) < 3:
        st.info(
            "Для прогноза нужно минимум 3 суток телеметрии с объёмом закачки "
            f"(q_day); сейчас доступно {len(all_dates)}."
        )
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        start_day, end_day = st.date_input(
            "Период истории",
            value=(all_dates[0], all_dates[-1]),
            min_value=all_dates[0],
            max_value=all_dates[-1],
            key="forecast_period",
        )
    with col2:
        period_days = st.selectbox(
            "Периодичность",
            options=[1, 7, 30],
            format_func=lambda d: PERIOD_LABELS[d],
            index=2,
            key="forecast_granularity",
        )
    with col3:
        horizon = st.number_input(
            "Горизонт, периодов вперёд",
            min_value=1,
            max_value=3660,
            value=36 if period_days == 30 else (52 if period_days == 7 else 1095),
            key="forecast_horizon",
        )

    try:
        res = lib.forecast_series(
            ctx.object_id,
            ctx.agg_id,
            start_day,
            end_day,
            period_days=period_days,
            horizon=int(horizon),
        )
    except InsufficientForecastData as error:
        if error.daily_count < 3:
            st.info(
                "В выбранном периоде меньше 3 суток с измеренным q_day — "
                "сузьте фильтр или уберите его."
            )
        else:
            st.warning(
                f"Полных периодов «{PERIOD_LABELS[period_days]}»: "
                f"{error.period_count} — нужно не менее 3."
            )
        return
    except ValueError as error:
        st.error(str(error))
        return

    history = res["history"]
    points = res["forecast"]
    ui.provenance(("Тренд-экстраполяция (МНК)", "warn"), (f"{len(history)} периодов истории", "ok"))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"Тренд, м³/{PERIOD_LABELS[period_days]}", fmt(res["trend_slope"], 1))
    m2.metric("Наивный ориентир (среднее)", fmt(res["naive_baseline"], 0))
    m3.metric(f"Прогноз, {PERIOD_LABELS[period_days]} {int(horizon)}", fmt(points[-1]["value"], 0))
    m4.metric(
        "Сумма за весь горизонт, м³", fmt(round(sum(point["value"] for point in points), 2), 0)
    )

    hist_df = pd.DataFrame({
        "Период": [point["period"] for point in history],
        "Значение": [point["value"] for point in history],
        "Ряд": "Факт",
    })
    fc_df = pd.DataFrame({
        "Период": [point["period"] for point in points],
        "Значение": [point["value"] for point in points],
        "Нижняя": [point["lower"] for point in points],
        "Верхняя": [point["upper"] for point in points],
        "Ряд": "Прогноз",
    })

    line = (
        alt
        .Chart(pd.concat([hist_df, fc_df], ignore_index=True))
        .mark_line(point=True)
        .encode(
            x=alt.X("Период:Q", title=f"Период ({PERIOD_LABELS[period_days]}; 0 = конец истории)"),
            y=alt.Y("Значение:Q", title="Объём, м³"),
            color=alt.Color(
                "Ряд:N", scale=alt.Scale(range=[ui.PALETTE["water_dark"], ui.PALETTE["accent"]])
            ),
        )
    )
    band = (
        alt
        .Chart(fc_df)
        .mark_area(opacity=0.15, color=ui.PALETTE["accent"])
        .encode(
            x="Период:Q",
            y="Нижняя:Q",
            y2="Верхняя:Q",
        )
    )
    st.altair_chart((band + line).properties(height=320), width="stretch")
