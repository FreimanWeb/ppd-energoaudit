"""💡 Мероприятия — реестр с ТЭО + оптимизация уставки с ограничениями.

База расчёта переключается:

* «текущий режим» — как раньше: годовой эффект текущего снимка, окупаемость
  = CAPEX / годовая экономия;
* «прогноз закачки» — годовой эффект масштабируется прогнозным объёмом закачки
  по годам горизонта (см. ``ppd_audit.measures.economics``), считаются NPV, IRR
  и дисконтированная окупаемость.
"""

from __future__ import annotations

import altair as alt
import lib
import pandas as pd
import streamlit as st
import ui

from tabs.common import Ctx, fmt


HORIZON_HELP = (
    "Сколько лет считать денежный поток. Прогноз закачки строится ровно на этот срок."
)
RATE_HELP = (
    "Годовая ставка дисконтирования для NPV и дисконтированной окупаемости. "
    "Задаётся инвестиционной политикой предприятия."
)
SCENARIO_LABEL = "сценарная оценка"


def render(ctx: Ctx) -> None:
    from ppd_audit.measures import DEFAULT_HORIZON_YEARS, suggest_measures
    from ppd_audit.optimize import optimize_setpoint

    st.subheader("Реестр мероприятий с ТЭО")
    if ctx.quality is not None and not ctx.quality.allows_economic_conclusions:
        st.warning(
            "Мероприятия не рассчитаны: выбранный режим непригоден для экономических выводов."
        )
        return
    ui.provenance(("Эвристическая оценка", "warn"), ("CAPEX — типовой", ""))
    st.caption(
        "Сценарные оценки — потенциал после диагностики; CAPEX и окупаемость для них не заданы."
    )
    _annual_runtime_caption(ctx)

    basis = st.radio(
        "База расчёта",
        ("Текущий режим (год)", "Прогноз закачки (горизонт)"),
        horizontal=True,
        key="measures_basis",
        help=(
            "«Текущий режим» — эффект сегодняшнего снимка, повторённый на год. "
            "«Прогноз закачки» — эффект каждого года масштабируется прогнозным "
            "объёмом закачки, плюс NPV/IRR/дисконтированная окупаемость."
        ),
    )

    if basis.startswith("Прогноз"):
        _render_horizon_economics(ctx, default_horizon=DEFAULT_HORIZON_YEARS)
    else:
        _render_annual_registry(suggest_measures(ctx.audit, ctx.tariff))

    st.markdown("---")
    _render_setpoint_optimizer(ctx, optimize_setpoint)


# ───────────────────────── база: текущий режим ─────────────────────────


def _annual_runtime_caption(ctx: Ctx) -> None:
    if ctx.source == "field_trip" and not ctx.scope.annual_runtime_is_assumed:
        st.caption(
            "Экономия за год рассчитана по T_год = "
            f"{fmt(ctx.scope.annual_runtime_hours, 1)} ч из YAML-паспорта."
        )
    elif ctx.scope.annual_runtime_is_assumed:
        st.caption(
            "Экономия за год — сценарий при T_год = 8760 ч; "
            "фактическая наработка требует уточнения."
        )
    else:
        st.caption(
            "Экономия за год рассчитана по T_год = "
            f"{fmt(ctx.scope.annual_runtime_hours, 1)} ч из телеметрии."
        )


def _render_annual_registry(evals) -> None:
    if not evals:
        st.info(
            "В текущем каталоге нет применимого мероприятия. "
            "Это не означает, что потери в норме."
        )
        return
    st.dataframe(
        {
            "Мероприятие": [e.name for e in evals],
            "Класс": [e.cls for e in evals],
            "Экономия, кВт·ч/год": [fmt(e.energy_saving_kwh, 0) for e in evals],
            "Экономия, тыс. ₽/год": [fmt(e.money_saving_krub, 1) for e in evals],
            "CAPEX, тыс. ₽": [
                "требует оценки" if e.cls == SCENARIO_LABEL else fmt(e.capex_krub, 0)
                for e in evals
            ],
            "Окупаемость, лет": [
                (
                    "требует оценки"
                    if e.cls == SCENARIO_LABEL
                    else fmt(e.payback_years, 2) if e.payback_years else "—"
                )
                for e in evals
            ],
        },
        width="stretch",
        hide_index=True,
    )


# ───────────────────────── база: прогноз закачки ─────────────────────────


def _base_annual_injection(ctx: Ctx) -> float:
    """Q_год базового режима, м³: подача × годовая наработка."""
    return float(ctx.audit.regime.q) * float(ctx.scope.annual_runtime_hours)


def _render_horizon_economics(ctx: Ctx, *, default_horizon: int) -> None:
    from ppd_audit.measures import (
        DEFAULT_DISCOUNT_RATE,
        InjectionProfile,
        suggest_measures_over_horizon,
    )

    col1, col2 = st.columns(2)
    with col1:
        horizon = int(
            st.number_input(
                "Горизонт, лет",
                min_value=1,
                max_value=10,
                value=default_horizon,
                step=1,
                key="measures_horizon_years",
                help=HORIZON_HELP,
            )
        )
    with col2:
        rate_percent = st.number_input(
            "Ставка дисконтирования, %/год",
            min_value=0.0,
            max_value=60.0,
            value=DEFAULT_DISCOUNT_RATE * 100.0,
            step=0.5,
            key="measures_discount_rate",
            help=RATE_HELP,
        )
    discount_rate = float(rate_percent) / 100.0

    base_annual = _base_annual_injection(ctx)
    profile = lib.injection_profile(
        ctx.object_id, ctx.agg_id, base_annual, horizon_years=horizon
    )
    if profile is None:
        st.warning(
            "Прогноз закачки не построен: нужно ≥3 полных месяца суточных объёмов "
            "(метрика q_day) в телеметрии этого агрегата. Экономика ниже посчитана при "
            "постоянном объёме закачки — то есть без учёта его динамики."
        )
        profile = InjectionProfile.flat(base_annual, horizon)

    ui.note(
        "Прогноз закачки — <b>статистическая экстраполяция тренда</b>, не "
        "гидродинамическая модель пласта и не план ГТМ. Годовой эффект каждого года "
        "масштабируется отношением прогнозного объёма закачки к объёму базового года. "
        "Результат — индикативный ориентир для ранжирования мероприятий, не проектное ТЭО."
    )
    if profile.extrapolated_tail:
        st.caption(
            "Горизонт длиннее построенного прогноза — хвост продлён последним "
            "прогнозным периодом."
        )

    _render_profile_summary(profile, horizon)
    _render_profile_chart(profile)

    evals = suggest_measures_over_horizon(
        ctx.audit, profile, tariff=ctx.tariff, discount_rate=discount_rate
    )
    if not evals:
        st.info(
            "В текущем каталоге нет применимого мероприятия. "
            "Это не означает, что потери в норме."
        )
        return

    st.markdown(f"**ТЭО на горизонте {horizon} лет** — при ставке {fmt(rate_percent, 1)} %/год")
    st.dataframe(
        pd.DataFrame(
            {
                "Мероприятие": [e.name for e in evals],
                "Класс": [e.cls for e in evals],
                "Эффект 1-го года, тыс. ₽": [fmt(e.years[0].money_saving_krub, 1) for e in evals],
                f"Экономия за {horizon} лет, тыс. ₽": [fmt(e.total_money_krub, 1) for e in evals],
                "CAPEX, тыс. ₽": [
                    "требует оценки" if e.cls == SCENARIO_LABEL else fmt(e.capex_krub, 0)
                    for e in evals
                ],
                "NPV, тыс. ₽": [
                    "требует оценки" if e.cls == SCENARIO_LABEL else fmt(e.npv_krub, 1)
                    for e in evals
                ],
                "IRR, %": [
                    (
                        "требует оценки"
                        if e.cls == SCENARIO_LABEL
                        else (fmt(e.irr * 100.0, 1) if e.irr is not None else "—")
                    )
                    for e in evals
                ],
                "Окупаемость диск., лет": [
                    (
                        "требует оценки"
                        if e.cls == SCENARIO_LABEL
                        else _payback_label(e.discounted_payback_years, horizon)
                    )
                    for e in evals
                ],
            }
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "IRR — «—», если мероприятие без CAPEX (окупается сразу) или поток не выходит "
        "в ноль на разумной ставке. «> горизонта» в окупаемости означает, что за "
        f"{horizon} лет накопленный дисконтированный поток не перекрыл CAPEX."
    )

    _render_cashflow_detail(evals, horizon)


def _payback_label(value: float | None, horizon: int) -> str:
    if value is None:
        return f"> {horizon}"
    if value == 0.0:
        return "сразу"
    return fmt(value, 2)


def _render_profile_summary(profile, horizon: int) -> None:
    growth = (
        (profile.annual_m3[-1] / profile.annual_m3[0] - 1.0) * 100.0
        if profile.annual_m3 and profile.annual_m3[0] > 0
        else None
    )
    cols = st.columns(4)
    cols[0].metric("Q_год базовый, м³", fmt(profile.base_annual_m3, 0))
    cols[1].metric("Q_год 1-го года, м³", fmt(profile.annual_m3[0], 0))
    cols[2].metric(f"Сумма за {horizon} лет, м³", fmt(profile.total_m3, 0))
    cols[3].metric(
        "Изменение к концу горизонта",
        f"{fmt(growth, 1)} %" if growth is not None else "—",
    )


def _render_profile_chart(profile) -> None:
    """Прогнозный профиль закачки по годам — одна серия, столбцы от нуля."""
    frame = pd.DataFrame(
        {
            "Год": [str(i + 1) for i in range(profile.horizon_years)],
            "Объём": profile.annual_m3,
            "К базе": [round(r, 3) for r in profile.ratios()],
        }
    )
    bars = (
        alt.Chart(frame)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=38)
        .encode(
            x=alt.X("Год:N", title="Год горизонта", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Объём:Q", title="Прогнозный объём закачки, м³"),
            color=alt.value(ui.PALETTE["accent"]),
            tooltip=[
                alt.Tooltip("Год:N"),
                alt.Tooltip("Объём:Q", title="Объём, м³", format=",.0f"),
                alt.Tooltip("К базе:Q", title="К базовому году, ×", format=".3f"),
            ],
        )
    )
    base_rule = (
        alt.Chart(pd.DataFrame({"База": [profile.base_annual_m3]}))
        .mark_rule(strokeDash=[6, 4], strokeWidth=2, color=ui.PALETTE["muted"])
        .encode(
            y="База:Q",
            tooltip=alt.Tooltip("База:Q", title="Q_год базовый, м³", format=",.0f"),
        )
    )
    st.altair_chart((bars + base_rule).properties(height=260), width="stretch")
    st.caption("Пунктир — Q_год базового режима, к которому нормируется эффект мероприятий.")


def _render_cashflow_detail(evals, horizon: int) -> None:
    st.markdown("**Денежный поток по годам**")
    names = [e.name for e in evals]
    chosen_name = st.selectbox(
        "Мероприятие", names, key="measures_cashflow_pick", label_visibility="collapsed"
    )
    chosen = next(e for e in evals if e.name == chosen_name)

    cols = st.columns(4)
    cols[0].metric(f"Экономия за {horizon} лет, тыс. ₽", fmt(chosen.total_money_krub, 1))
    cols[1].metric("То же дисконтированно, тыс. ₽", fmt(chosen.total_discounted_krub, 1))
    cols[2].metric(
        "NPV, тыс. ₽",
        "требует оценки" if chosen.cls == SCENARIO_LABEL else fmt(chosen.npv_krub, 1),
    )
    cols[3].metric(
        "Окупаемость диск., лет",
        "требует оценки"
        if chosen.cls == SCENARIO_LABEL
        else _payback_label(chosen.discounted_payback_years, horizon),
    )

    long = pd.DataFrame(
        [
            {"Год": y.year, "Значение": y.cumulative_krub, "Поток": "Накопленный"}
            for y in chosen.years
        ]
        + [
            {
                "Год": y.year,
                "Значение": y.cumulative_discounted_krub,
                "Поток": "Накопленный дисконтированный",
            }
            for y in chosen.years
        ]
    )
    # Две серии различаются и цветом, и типом штриха — идентичность не держится
    # на одном только цвете.
    domain = ["Накопленный", "Накопленный дисконтированный"]
    lines = (
        alt.Chart(long)
        .mark_line(point=alt.OverlayMarkDef(size=60), strokeWidth=2)
        .encode(
            x=alt.X("Год:O", title="Год горизонта", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Значение:Q", title="Накопленная экономия, тыс. ₽"),
            color=alt.Color(
                "Поток:N",
                title=None,
                scale=alt.Scale(domain=domain, range=[ui.PALETTE["accent"], ui.PALETTE["ok"]]),
                legend=alt.Legend(orient="top"),
            ),
            strokeDash=alt.StrokeDash(
                "Поток:N",
                scale=alt.Scale(domain=domain, range=[[1, 0], [6, 4]]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("Поток:N", title="Поток"),
                alt.Tooltip("Год:O"),
                alt.Tooltip("Значение:Q", title="Тыс. ₽", format=",.1f"),
            ],
        )
    )
    layers = [lines]
    if chosen.capex_krub > 0 and chosen.cls != SCENARIO_LABEL:
        capex_frame = pd.DataFrame({"CAPEX": [chosen.capex_krub]})
        layers.append(
            alt.Chart(capex_frame)
            .mark_rule(strokeDash=[2, 3], strokeWidth=2, color=ui.PALETTE["muted"])
            .encode(
                y="CAPEX:Q",
                tooltip=alt.Tooltip("CAPEX:Q", title="CAPEX, тыс. ₽", format=",.0f"),
            )
        )
        layers.append(
            alt.Chart(capex_frame)
            .mark_text(align="left", dx=6, dy=-8, color=ui.PALETTE["muted"], fontSize=12)
            .encode(y="CAPEX:Q", text=alt.value("CAPEX"))
        )
    st.altair_chart(alt.layer(*layers).properties(height=300), width="stretch")

    st.dataframe(
        pd.DataFrame(
            {
                "Год": [y.year for y in chosen.years],
                "Закачка, м³": [fmt(y.injection_m3, 0) for y in chosen.years],
                "К базе, ×": [fmt(y.volume_ratio, 3) for y in chosen.years],
                "Экономия, кВт·ч": [fmt(y.energy_saving_kwh, 0) for y in chosen.years],
                "Экономия, тыс. ₽": [fmt(y.money_saving_krub, 1) for y in chosen.years],
                "Коэф. дисконта": [fmt(y.discount_factor, 4) for y in chosen.years],
                "Дисконт., тыс. ₽": [fmt(y.discounted_krub, 1) for y in chosen.years],
                "Накопл. диск., тыс. ₽": [
                    fmt(y.cumulative_discounted_krub, 1) for y in chosen.years
                ],
            }
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(chosen.note)


# ───────────────────────── оптимизация уставки ─────────────────────────


def _render_setpoint_optimizer(ctx: Ctx, optimize_setpoint) -> None:
    st.subheader("Оптимизация уставки (с ограничениями)")
    ui.provenance(("Расчётная оценка", "warn"), ("Ограничения — конфиг", ""))
    opt = optimize_setpoint(ctx.audit, lib.constraints())
    cc = st.columns(4)
    cc[0].metric("p_вых текущее, МПа", fmt(opt.current_p_out, 2))
    cc[1].metric("p_вых оптимум, МПа", fmt(opt.optimal_p_out, 2))
    cc[2].metric("Экономия, кВт·ч/год", fmt(opt.saving_kwh_year, 0))
    cc[3].metric("Частота ПЧ, Гц", fmt(opt.vfd_freq_hz, 1) if opt.vfd_freq_hz else "—")

    horizon = st.session_state.get("measures_horizon_years")
    basis = st.session_state.get("measures_basis") or ""
    if basis.startswith("Прогноз") and horizon and (opt.saving_kwh_year or 0) > 0:
        profile = lib.injection_profile(
            ctx.object_id, ctx.agg_id, _base_annual_injection(ctx), horizon_years=int(horizon)
        )
        if profile is not None:
            total_kwh = (opt.saving_kwh_year or 0.0) * sum(profile.ratios())
            st.caption(
                f"С учётом прогноза закачки за {int(horizon)} лет: "
                f"{fmt(total_kwh, 0)} кВт·ч ≈ {fmt(total_kwh * ctx.tariff / 1000.0, 1)} тыс. ₽ "
                "(без дисконтирования)."
            )

    for n in opt.notes:
        (st.success if opt.within_constraints else st.warning)(n)
