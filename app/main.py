"""Цифровой энергоаудит ППД — дашборд (Streamlit).

Запуск:  streamlit run app/main.py
Экраны (от общего к частному): Обзор · Режимный снимок · Телеметрия · Прогноз
закачки · Схема ППД · Карта потерь · Рабочая точка · Мероприятия · Новый
объект · Формулы.

main.py — только каркас: сайдбар (выбор объекта/агрегата), hero-хедер и роутинг
вкладок. Содержимое каждой вкладки — в app/tabs/<имя>.py (render(ctx)).
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, time, timedelta


# каталог app/ для import lib/ui/tabs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lib
import streamlit as st
import ui
from ppd_telemetry_calendar import render_calendar, selected_calendar_date, visible_calendar_month
from tabs import (
    formulas,
    forecast,
    losses,
    measures,
    new_object,
    overview,
    scheme,
    snapshot,
    telemetry,
    working_point,
)
from tabs.common import WATER_EMOJI, Ctx, fmt


st.set_page_config(page_title="Энергоаудит ППД", page_icon="⚡", layout="wide")
ui.inject_css()

# ───────────────────────── Sidebar: выбор объекта ─────────────────────────

st.sidebar.title("⚡ Энергоаудит ППД")
mode = st.sidebar.radio(
    "Режим", ("Анализ по телеметрии", "Выезд", "Просмотр телеметрии")
)
index = lib.object_index()
waters = sorted(
    {o["water"] for o in index},
    key=lambda w: lib.WATER_ORDER.index(w) if w in lib.WATER_ORDER else 9,
)
sel_waters = st.sidebar.multiselect("Тип воды", waters, default=waters)
ngdus = sorted({o["ngdu"] for o in index})
sel_ngdus = st.sidebar.multiselect("НГДУ", ngdus, default=ngdus)
flt = [o for o in index if o["water"] in sel_waters and o["ngdu"] in sel_ngdus] or index

obj_labels = {
    f"{'' if mode == 'Выезд' else ('🟢 ' if o['has_telemetry'] else '⚪ ')}"
    f"{o['name']} · {o['ngdu']}  ·  "
    f"{WATER_EMOJI.get(o['water'], '')} {o['water']}": o["id"]
    for o in flt
}
object_options = list(obj_labels)
default_object_index = next(
    (index for index, label in enumerate(object_options) if "КНС-54" in label), 0
)
obj_choice = st.sidebar.selectbox("Объект", object_options, index=default_object_index)
object_id = obj_labels[obj_choice]
selected = next(o for o in index if o["id"] == object_id)

agg_ids = selected["aggregate_ids"]
agg_id = st.sidebar.selectbox("Агрегат", agg_ids)
if mode == "Выезд":
    try:
        obj, audit = lib.get_field_trip_audit(object_id, agg_id)
    except (ArithmeticError, KeyError, ValueError) as exc:
        st.warning(f"Невозможно рассчитать выезд для {selected['name']} / {agg_id}: {exc}")
        st.stop()
    eta_ratio = audit.regime.eta_unit / audit.regime.eta_nom if audit.regime.eta_nom else 1.0
    eta_tone = "ok" if eta_ratio >= 0.9 else ("warn" if eta_ratio >= 0.78 else "bad")
    ctx = Ctx(
        object_id=object_id,
        agg_id=agg_id,
        obj=obj,
        agg=audit.spec,
        audit=audit,
        tariff=lib.tariff(),
        selected_date=date.min,
        snapshot_timestamp=datetime.min,
        scope=lib.field_trip_scope(audit.spec.regime),
        source="field_trip",
    )
    ui.hero(
        f"{obj.name} · {agg_id} · НГДУ {selected['ngdu']}",
        "Выездной аудит · YAML-паспорт",
        [
            (f"{WATER_EMOJI.get(obj.water_type.value, '')} {obj.water_type.value} вода", ""),
            (f"ветка: {obj.branch.value}", ""),
            (f"насос: {audit.pump_kind}", ""),
            (f"КПД {fmt(audit.regime.eta_unit, 3)} / ном {fmt(audit.regime.eta_nom, 3)}", eta_tone),
            (f"УРЭ {fmt(audit.sec_fact, 2)} кВт·ч/м³", ""),
        ],
    )
    field_trip_tabs = [
        ("📋 Обзор", overview),
        ("📉 Карта потерь", losses),
        ("📈 Рабочая точка", working_point),
        ("💡 Мероприятия", measures),
        ("🧮 Формулы", formulas),
    ]
    for tab, (_, module) in zip(
        st.tabs([item[0] for item in field_trip_tabs]), field_trip_tabs, strict=True
    ):
        with tab:
            module.render(ctx)
    st.stop()
dates = lib.telemetry_dates(object_id, agg_id)
if not dates:
    st.warning(f"Нет телеметрии для {selected['name']} / {agg_id}.")
    st.stop()

if mode == "Просмотр телеметрии":
    period = st.sidebar.date_input(
        "Период телеметрии",
        value=(min(dates), max(dates)),
        min_value=min(dates),
        max_value=max(dates),
    )
    if not isinstance(period, tuple) or len(period) != 2:
        st.info("Выберите начало и конец периода.")
        st.stop()
    telemetry.render_period(object_id, agg_id, *period)
    st.stop()

selected_key = f"telemetry-date-{object_id}-{agg_id}"
calendar_key = f"{selected_key}-picker"
selected_date = selected_calendar_date(
    key=calendar_key,
    fallback=st.session_state.get(selected_key, max(dates)),
)
visible_year, visible_month = visible_calendar_month(key=calendar_key, fallback=selected_date)
month_dates = [
    day for day in dates if (day.year, day.month) == (visible_year, visible_month)
]
date_statuses = lib.telemetry_date_statuses(object_id, agg_id, month_dates)
with st.sidebar:
    selected_date = render_calendar(
        selected_day=selected_date,
        statuses=date_statuses,
        min_day=min(dates),
        max_day=max(dates),
        key=calendar_key,
    )
st.session_state[selected_key] = selected_date
if selected_date not in date_statuses:
    st.warning(f"Нет телеметрии за {selected_date} для {selected['name']} / {agg_id}.")
    st.stop()
start = datetime.combine(selected_date, time.min)
end = start + timedelta(days=1)
status = lib.telemetry_day_status(object_id, agg_id, selected_date)
if status == "insufficient":
    try:
        lib.get_audit(object_id, agg_id, start, end)
    except (ArithmeticError, KeyError, ValueError) as exc:
        st.warning(f"Нет пригодного режима за {selected_date}: {exc}")
    else:
        st.warning(f"Нет пригодного режима за {selected_date}: телеметрия недостаточна.")
    telemetry.render_day(object_id, agg_id, selected_date)
    st.stop()
is_snapshot = status == "snapshot"
if is_snapshot:
    st.warning(
        "Давления синхронны с работающим агрегатом менее чем для 80% точек мощности. "
        "Поэтому показатели по давлению рассчитаны как режимный снимок, а не за сутки."
    )
snapshots = lib.telemetry_snapshots(object_id, agg_id, start, end)
excluded_by_manifold = lib.excluded_snapshots_by_manifold_pressure(
    object_id, agg_id, start, end
)
if excluded_by_manifold:
    st.warning(
        f"Исключено снимков из расчёта НА: {excluded_by_manifold}. "
        "Причина: p_вых ≤ p_БГ."
    )
if not snapshots:
    st.warning(
        f"Нет пригодного режимного снимка за {selected_date}: нужна устойчивая пара "
        "p_вх/p_вых и положительная мощность не дальше 5 минут."
    )
    telemetry.render_day(object_id, agg_id, selected_date)
    st.stop()
snapshot_key = lib.snapshot_selection_key(object_id, agg_id, selected_date)
snapshot_by_timestamp = {snapshot.timestamp.isoformat(): snapshot for snapshot in snapshots}
st.session_state.setdefault(snapshot_key, snapshots[-1].timestamp.isoformat())
if st.session_state[snapshot_key] not in snapshot_by_timestamp:
    st.session_state[snapshot_key] = snapshots[-1].timestamp.isoformat()
snapshot_timestamp = datetime.fromisoformat(st.session_state[snapshot_key])
try:
    obj = lib.get_object(object_id, start)
    snapshot_audit = lib.get_snapshot_audit(
        object_id,
        agg_id,
        start,
        end,
        snapshot_timestamp,
    )
except (ArithmeticError, KeyError, ValueError) as exc:
    st.warning(f"Нет пригодного режима за {selected_date}: {exc}")
    telemetry.render_day(object_id, agg_id, selected_date)
    st.stop()
audit = snapshot_audit.audit
agg = audit.spec
scope = lib.result_scope_for(
    object_id,
    agg_id,
    end,
    audit.spec.regime,
    daily_pressure_coverage_is_complete=False,
)

clarifications = lib.open_clarifications(object_id, agg_id)
if clarifications:
    with st.sidebar.expander(f"Требуют уточнения ({len(clarifications)})"):
        for item in clarifications:
            field = {
                "t_year": "T_год",
                "transmission_eff": "КПД трансмиссии",
                "pump_eta_nom": "КПД насоса",
                "motor_eta_nom": "КПД ЭД",
            }.get(item["field"], item["field"])
            st.caption(
                f"{field} = {item['provisional_value']}"
            )
            st.caption(item["reason"])

ctx = Ctx(
    object_id=object_id,
    agg_id=agg_id,
    obj=obj,
    agg=agg,
    audit=audit,
    tariff=lib.tariff(),
    selected_date=selected_date,
    snapshot_timestamp=snapshot_timestamp,
    scope=scope,
)


# ───────────────────────── Hero-хедер ─────────────────────────

_eta_ratio = (audit.regime.eta_unit / audit.regime.eta_nom) if audit.regime.eta_nom else 1.0
_eta_tone = "ok" if _eta_ratio >= 0.9 else ("warn" if _eta_ratio >= 0.78 else "bad")
ui.hero(
    f"{obj.name} · {agg_id} · НГДУ {selected['ngdu']}",
    f"Цифровой энергоаудит ППД · SQLite · сутки: {selected_date}",
    [
        (f"{WATER_EMOJI.get(obj.water_type.value, '')} {obj.water_type.value} вода", ""),
        (f"ветка: {obj.branch.value}", ""),
        (f"насос: {audit.pump_kind}", ""),
        (f"КПД {fmt(audit.regime.eta_unit, 3)} / ном {fmt(audit.regime.eta_nom, 3)}", _eta_tone),
        (f"УРЭ {fmt(audit.sec_fact, 2)} кВт·ч/м³", ""),
    ],
)

# ───────────────────────── Вкладки (от общего к частному) ─────────────────────────

TABS = [
    ("📋 Обзор", overview),
    ("🎯 Режимный снимок", snapshot),
    ("📊 Телеметрия", telemetry),
    ("📈 Прогноз закачки", forecast),
    ("🗺️ Схема ППД", scheme),
    ("📉 Карта потерь", losses),
    ("📈 Рабочая точка", working_point),
    ("💡 Мероприятия", measures),
    ("🧩 Новый объект", new_object),
    ("🧮 Формулы", formulas),
]

for tab, (_, module) in zip(st.tabs([t for t, _ in TABS]), TABS, strict=True):
    with tab:
        module.render(ctx)
