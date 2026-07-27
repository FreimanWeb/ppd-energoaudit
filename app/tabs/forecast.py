"""📈 Прогноз закачки — статистическая экстраполяция тренда на будущие периоды.

Использует суточные объёмы закачки/перекачки (метрика ``q_day`` из телеметрии,
см. ``services/telemetry_series.py``) и трендовую экстраполяцию из
``core/reservoir/forecast.py``. Это НЕ гидродинамическая модель пласта —
явно показываем это прямо на вкладке, а не только в докстринге ядра.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import altair as alt
import lib
import pandas as pd
import streamlit as st
import ui

from ppd_audit.core.reservoir.forecast import aggregate_daily_to_periods, forecast_injection
from tabs.common import Ctx, fmt


PERIOD_LABELS = {1: "сутки", 7: "неделя", 30: "месяц"}


def _daily_q_series(object_id: str, aggregate_id: str, start_day, end_day) -> list[tuple[str, float]]:
    """Суточные объёмы (q_day) по датам, отсортированные по времени."""
    rows = lib.telemetry_for_period(object_id, aggregate_id, start_day, end_day)
    by_date: dict[str, float] = {}
    for row in rows:
        if row["metric"] != "q_day":
            continue
        # приоритет — значение агрегата; станционное берём только если своего нет
        day_key = row["timestamp"][:10]
        if row["is_station"] and day_key in by_date:
            continue
        if (not row["is_station"]) or day_key not in by_date:
            by_date[day_key] = row["value"]
    return sorted(by_date.items())


def render(ctx: Ctx) -> None:
    st.subheader("Прогноз объёма закачки")
    ui.note(
        "Статистическая экстраполяция линейного тренда (МНК) по факту — "
        "<b>не гидродинамическая модель пласта</b>. Не учитывает план ГТМ, "
        "фонд скважин, ограничения приёмистости/давления нагнетания. "
        "Используйте только как индикативный, а не проектный ориентир."
    )

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
            "Периодичность", options=[1, 7, 30],
            format_func=lambda d: PERIOD_LABELS[d], index=2, key="forecast_granularity",
        )
    with col3:
        horizon = st.number_input(
            "Горизонт, периодов вперёд", min_value=1, max_value=1000,
            value=36 if period_days == 30 else (52 if period_days == 7 else 1095),
            key="forecast_horizon",
        )

    daily = _daily_q_series(ctx.object_id, ctx.agg_id, start_day, end_day)
    if len(daily) < 3:
        st.info("В выбранном периоде меньше 3 суток с измеренным q_day — сузьте фильтр или уберите его.")
        return

    values = [v for _, v in daily]
    history = aggregate_daily_to_periods(values, days_per_period=period_days) if period_days > 1 else values
    if len(history) < 3:
        st.warning(
            f"При периодичности «{PERIOD_LABELS[period_days]}» из выбранного диапазона получилось "
            f"только {len(history)} полных периода(ов) — нужно ≥3. Расширьте период истории или "
            "выберите более мелкую периодичность."
        )
        return

    try:
        res = forecast_injection(history, horizon=int(horizon))
    except ValueError as e:
        st.error(str(e))
        return

    ui.provenance(("Тренд-экстраполяция (МНК)", "warn"), (f"{len(history)} периодов истории", "ok"))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"Тренд, м³/{PERIOD_LABELS[period_days]}", fmt(res.trend_slope, 1))
    m2.metric("Наивный ориентир (среднее)", fmt(res.naive_baseline, 0))
    m3.metric(f"Прогноз, {PERIOD_LABELS[period_days]} {int(horizon)}", fmt(res.points[-1].value, 0))
    m4.metric("Сумма за весь горизонт, м³", fmt(res.total(), 0))

    hist_df = pd.DataFrame({
        "Период": list(range(-len(history) + 1, 1)),
        "Значение": history,
        "Ряд": "Факт",
    })
    fc_df = pd.DataFrame({
        "Период": [p.period for p in res.points],
        "Значение": [p.value for p in res.points],
        "Нижняя": [p.lower for p in res.points],
        "Верхняя": [p.upper for p in res.points],
        "Ряд": "Прогноз",
    })

    line = alt.Chart(pd.concat([hist_df, fc_df], ignore_index=True)).mark_line(point=True).encode(
        x=alt.X("Период:Q", title=f"Период ({PERIOD_LABELS[period_days]}; 0 = конец истории)"),
        y=alt.Y("Значение:Q", title="Объём, м³"),
        color=alt.Color("Ряд:N", scale=alt.Scale(range=[ui.PALETTE["water_dark"], ui.PALETTE["accent"]])),
    )
    band = alt.Chart(fc_df).mark_area(opacity=0.15, color=ui.PALETTE["accent"]).encode(
        x="Период:Q", y="Нижняя:Q", y2="Верхняя:Q",
    )
    st.altair_chart((band + line).properties(height=320), width="stretch")

    st.caption(res.note)
