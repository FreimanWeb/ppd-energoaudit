"""Прогноз CRM — подача агрегатов по модели пласта рядом с фактом.

Модель (ARX/CRM по объекту) обучается и считается внешним инструментом;
дашборд читает её выгрузки из ``data/crm/<объект>/<прогон>/`` и кладёт
суточные объёмы прогноза на один график с фактом из телеметрии.
"""

from __future__ import annotations

from datetime import date, timedelta

import altair as alt
import lib
import pandas as pd
import streamlit as st
import ui

from tabs.common import Ctx, fmt


STATION = "Станция (сумма)"

# Сколько суток факта показывать до начала прогноза.
HISTORY_DAYS = 30


def _iso_to_date(value: str) -> date:
    return date.fromisoformat(value)


def _fact_series(
    object_id: str, aggregates: list[str], start: date, end: date
) -> dict[date, float]:
    """Суточная закачка по факту, суммой по указанным агрегатам."""
    totals: dict[date, float] = {}
    for aggregate in aggregates:
        for day, value in lib.daily_injection_series(object_id, aggregate, start, end):
            key = _iso_to_date(day)
            totals[key] = totals.get(key, 0.0) + value
    return totals


def render(ctx: Ctx) -> None:
    st.subheader("Прогноз подачи по CRM-модели")

    runs = lib.crm_runs(ctx.object_id)
    if not runs:
        st.info("Нет данных прогноза для этого объекта.")
        return

    if len(runs) > 1:
        titles = {run["title"]: run["code"] for run in runs}
        chosen = st.radio(
            "Сценарий прогноза", list(titles), horizontal=True, key=f"crm-run-{ctx.object_id}"
        )
        run_code = titles[chosen]
    else:
        run_code = runs[0]["code"]

    forecast = lib.crm_daily_forecast(ctx.object_id, run_code)
    if forecast is None:
        st.warning("Прогон не найден — возможно, папку переименовали. Обновите страницу.")
        return
    if "error" in forecast:
        st.error(f"Выгрузка прогноза не читается: {forecast['error']}")
        return
    if not forecast["total"]:
        st.warning(
            "В выгрузке нет ни одних полных суток: все дни горизонта оборваны по краям."
        )
        return

    units = sorted(forecast["by_unit"])
    choice = st.selectbox(
        "Показатель", [STATION, *units], key=f"crm-unit-{ctx.object_id}-{run_code}"
    )
    series = (
        forecast["total"] if choice == STATION else forecast["by_unit"][choice]
    )
    predicted = {_iso_to_date(day): value for day, value in series}

    first, last = min(predicted), max(predicted)
    fact_aggregates = units if choice == STATION else [choice]
    fact = _fact_series(
        ctx.object_id, fact_aggregates, first - timedelta(days=HISTORY_DAYS), last
    )

    ui.provenance(
        (f"Модель: {forecast['model'] or 'не указана'}", ""),
        ("Сценарий с событиями", "warn") if forecast["events"] else ("Базовый сценарий", ""),
        (f"шаг выгрузки {fmt(forecast['interval_hours'], 1)} ч", ""),
    )

    overlap = sorted(set(predicted) & set(fact))
    left, right = st.columns(2)
    left.metric(
        "Прогноз, м³/сут в среднем",
        fmt(sum(predicted.values()) / len(predicted), 0),
        help=f"Горизонт {first:%d.%m.%Y} — {last:%d.%m.%Y}, {len(predicted)} полных суток.",
    )
    right.metric(
        "Факт на перекрытии, м³/сут",
        fmt(sum(fact[day] for day in overlap) / len(overlap), 0) if overlap else "—",
        help=(
            f"{len(overlap)} суток, где прогноз и телеметрия перекрываются."
            if overlap
            else "Прогноз начинается позже последних суток телеметрии."
        ),
    )

    frame = pd.concat(
        [
            pd.DataFrame({
                "Дата": list(fact),
                "Объём": list(fact.values()),
                "Ряд": "Факт (телеметрия)",
            }),
            pd.DataFrame({
                "Дата": list(predicted),
                "Объём": list(predicted.values()),
                "Ряд": "Прогноз CRM",
            }),
        ],
        ignore_index=True,
    )
    axis = alt.Axis(format="%d.%m.%Y", labelAngle=-40)
    chart = alt.Chart(frame).mark_line().encode(
        x=alt.X("Дата:T", title=None, axis=axis),
        y=alt.Y("Объём:Q", title="Подача, м³/сут"),
        color=alt.Color(
            "Ряд:N",
            title=None,
            scale=alt.Scale(
                domain=["Факт (телеметрия)", "Прогноз CRM"],
                range=[ui.PALETTE["water_dark"], ui.PALETTE["accent"]],
            ),
        ),
        tooltip=[
            alt.Tooltip("Дата:T", format="%d.%m.%Y"),
            alt.Tooltip("Объём:Q", format=".1f"),
            "Ряд:N",
        ],
    )
    # Граница факта: правее неё сравнивать не с чем — это уже чистый прогноз.
    if fact:
        edge = alt.Chart(pd.DataFrame({"Дата": [max(fact)]})).mark_rule(
            strokeDash=[4, 4], color=ui.PALETTE["muted"]
        ).encode(x=alt.X("Дата:T", axis=axis))
        chart = edge + chart
    st.altair_chart(chart.properties(height=340), width="stretch")

    st.caption(
        "Факт — по тем же агрегатам, что в модели"
        + (f" ({', '.join(units)})" if choice == STATION and len(units) > 1 else "")
        + ". Пунктир — последние сутки телеметрии."
    )
