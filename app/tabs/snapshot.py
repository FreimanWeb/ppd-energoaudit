"""Режимный расчёт — расчёт по точной паре давлений на выбранный момент."""

from __future__ import annotations

from datetime import datetime, timedelta

import lib
import streamlit as st
import ui

from tabs.common import Ctx, fmt


# Ключи основания приходят из ядра латиницей — на экран выводим по-русски.
BASIS_LABELS = {"pressure": "Давление", "flow": "Подача", "power": "Мощность"}


def _gap(value: timedelta | None) -> str:
    if value is None:
        return "нет точки"
    seconds = int(value.total_seconds())
    return f"{seconds // 60} мин {seconds % 60} с"


def _label(snapshot) -> str:
    stability = "устойчиво" if snapshot.is_stable else "переход"
    return (
        f"{snapshot.timestamp:%H:%M:%S} · Δp {snapshot.p_out_mpa - snapshot.p_in_mpa:.3f} МПа"
        f" · {stability}"
    )


def render(ctx: Ctx) -> None:
    """Показать самостоятельный режимный расчёт, не затрагивая суточный экран."""
    object_id, aggregate_id, selected_date = ctx.object_id, ctx.agg_id, ctx.selected_date
    start = datetime.combine(selected_date, datetime.min.time())
    end = start + timedelta(days=1)
    st.subheader("Режимный расчёт")
    ui.provenance(("Давления: последнее изменение до выбранного момента", "ok"))
    snapshots = lib.telemetry_snapshots(object_id, aggregate_id, start, end)
    if not snapshots:
        st.warning(
            "Нет пригодного режима: нужна устойчивая пара p_вх/p_вых "
            "в момент положительной мощности."
        )
        return

    snapshot_key = lib.snapshot_selection_key(object_id, aggregate_id, selected_date)
    snapshot_by_timestamp = {snapshot.timestamp.isoformat(): snapshot for snapshot in snapshots}
    st.session_state.setdefault(snapshot_key, snapshots[-1].timestamp.isoformat())
    selected_timestamp = st.selectbox(
        "Показатель давления",
        list(snapshot_by_timestamp),
        format_func=lambda timestamp: _label(snapshot_by_timestamp[timestamp]),
        key=snapshot_key,
    )
    selected = snapshot_by_timestamp[selected_timestamp]
    try:
        result = lib.get_snapshot_audit(
            object_id, aggregate_id, start, end, selected.timestamp
        )
    except (ArithmeticError, KeyError, ValueError) as exc:
        st.warning(f"Нельзя построить расчёт на выбранный момент: {exc}")
        return

    audit, snapshot = result.audit, result.snapshot
    if result.quality.status == "unfit":
        st.error("Режим непригоден: " + " ".join(issue.message for issue in result.quality.issues))
    st.markdown("### Суточный факт")
    if audit.spec.regime.w is None or audit.spec.regime.q_day is None:
        st.info("Нет W и Q_сут: суточный фактический УРЭ не вычисляется.")
    else:
        st.metric("УРЭ факт за сутки, кВт·ч/м³", fmt(audit.sec_fact, 3))
        st.caption("Факт за сутки: W / Q_сут.")

    st.markdown("### Режим")
    st.markdown("**Основание расчётных показателей**")
    st.dataframe(
        {
            "Показатель": [BASIS_LABELS.get(key, key) for key in result.quality.basis],
            "Основание": [
                value.replace("в момент снимка", "на выбранный момент")
                for value in result.quality.basis.values()
            ],
        },
        hide_index=True,
        width="stretch",
    )
    if result.sources:
        st.markdown("**Источники расчётных входов**")
        st.dataframe(
            {"Показатель": list(result.sources), "Источник": list(result.sources.values())},
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("Источники не сохранены у этой ранее загруженной телеметрии.")
    left, right = st.columns(2)
    with left:
        st.metric("p_вх, МПа", fmt(snapshot.p_in_mpa, 3))
        st.metric("p_вых, МПа", fmt(snapshot.p_out_mpa, 3))
        st.metric("p_БГ, МПа", fmt(snapshot.p_bg_mpa, 3))
    with right:
        st.metric("УРЭ расчётный, кВт·ч/м³", fmt(audit.sec_calc, 3))
        st.metric("КПД на выбранный момент, о.е.", fmt(audit.regime.eta_unit, 3))
        st.caption(
            f"Момент: {snapshot.timestamp:%d.%m.%Y %H:%M:%S}; "
            f"P_эл не менялась: {_gap(snapshot.power_age)}; "
            f"p_БГ не менялось: {_gap(snapshot.p_bg_age)}."
        )

    st.markdown("### Годовой сценарий")
    ui.provenance(("Годовая оценка — сценарий, не факт", "warn"))
    st.caption("Сценарий по выбранному давлению, суточным Q/W/T и T_год.")
    first, second = st.columns(2)
    first.metric("ΔW по КПД, кВт·ч/год", fmt(audit.dw_efficiency, 0))
    second.metric("ΔW по дросселированию, кВт·ч/год", fmt(audit.dw_throttle, 0))
