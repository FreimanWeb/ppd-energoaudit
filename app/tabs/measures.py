"""💡 Мероприятия — реестр с ТЭО + оптимизация уставки с ограничениями."""

from __future__ import annotations

import lib
import streamlit as st
import ui

from tabs.common import Ctx, fmt


def render(ctx: Ctx) -> None:
    from ppd_audit.measures import suggest_measures
    from ppd_audit.optimize import optimize_setpoint

    st.subheader("Реестр мероприятий с ТЭО")
    ui.provenance(("Эвристическая оценка", "warn"), ("CAPEX — типовой", ""))
    st.caption(
        "Сценарные оценки — потенциал после диагностики; CAPEX и окупаемость для них не заданы."
    )
    if ctx.scope.annual_runtime_is_assumed:
        st.caption(
            "Экономия за год — сценарий при T_год = 8760 ч; "
            "фактическая наработка требует уточнения."
        )
    else:
        st.caption(
            "Экономия за год рассчитана по T_год = "
            f"{fmt(ctx.scope.annual_runtime_hours, 1)} ч из телеметрии."
        )
    evals = suggest_measures(ctx.audit, ctx.tariff)
    if evals:
        st.dataframe(
            {
                "Мероприятие": [e.name for e in evals],
                "Класс": [e.cls for e in evals],
                "Экономия, кВт·ч/год": [fmt(e.energy_saving_kwh, 0) for e in evals],
                "Экономия, тыс. ₽/год": [fmt(e.money_saving_krub, 1) for e in evals],
                "CAPEX, тыс. ₽": [
                    "требует оценки" if e.cls == "сценарная оценка" else fmt(e.capex_krub, 0)
                    for e in evals
                ],
                "Окупаемость, лет": [
                    (
                        "требует оценки"
                        if e.cls == "сценарная оценка"
                        else fmt(e.payback_years, 2) if e.payback_years else "—"
                    )
                    for e in evals
                ],
            },
            width="stretch",
            hide_index=True,
        )
    else:
        st.info(
            "В текущем каталоге нет применимого мероприятия. "
            "Это не означает, что потери в норме."
        )

    st.markdown("---")
    st.subheader("Оптимизация уставки (с ограничениями)")
    ui.provenance(("Расчётная оценка", "warn"), ("Ограничения — конфиг", ""))
    opt = optimize_setpoint(ctx.audit, lib.constraints())
    cc = st.columns(4)
    cc[0].metric("p_вых текущее, МПа", fmt(opt.current_p_out, 2))
    cc[1].metric("p_вых оптимум, МПа", fmt(opt.optimal_p_out, 2))
    cc[2].metric("Экономия, кВт·ч/год", fmt(opt.saving_kwh_year, 0))
    cc[3].metric("Частота ПЧ, Гц", fmt(opt.vfd_freq_hz, 1) if opt.vfd_freq_hz else "—")
    for n in opt.notes:
        (st.success if opt.within_constraints else st.warning)(n)
