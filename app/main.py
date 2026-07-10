"""Цифровой энергоаудит ППД — дашборд (Streamlit).

Запуск:  streamlit run app/main.py
Экраны (от общего к частному): Обзор · Схема ППД · Карта потерь · Рабочая точка ·
Мероприятия · Новый объект · Формулы · Качество данных.

main.py — только каркас: сайдбар (выбор объекта/агрегата), hero-хедер и роутинг
вкладок. Содержимое каждой вкладки — в app/tabs/<имя>.py (render(ctx)).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # каталог app/ для import lib/ui/tabs

import lib  # noqa: E402  data-слой (настраивает путь к src/)
import streamlit as st  # noqa: E402
import ui  # noqa: E402  дизайн-система (CSS + компоненты)
from tabs import (formulas, losses, measures, new_object, overview,  # noqa: E402
                  quality, scheme, working_point)
from tabs.common import WATER_EMOJI, Ctx, fmt  # noqa: E402

st.set_page_config(page_title="Энергоаудит ППД", page_icon="⚡", layout="wide")
ui.inject_css()

# ───────────────────────── Доступ по паролю ─────────────────────────
# Показываем форму один раз за сессию; после верного пароля она исчезает
# и больше не пересчитывает страницу на каждый нажатый символ.

if not st.session_state.get("_authed", False):
    st.markdown("### 🔒 Доступ к дашборду")
    with st.form("_login", clear_on_submit=False):
        pwd = st.text_input("Пароль", type="password")
        ok = st.form_submit_button("Войти")
    if ok:
        if pwd == st.secrets.get("app_password", None):
            st.session_state["_authed"] = True
            st.rerun()
        else:
            st.error("Неверный пароль.")
    st.stop()

# ───────────────────────── Sidebar: выбор объекта ─────────────────────────

st.sidebar.title("⚡ Энергоаудит ППД")
index = lib.object_index()
waters = sorted({o["water"] for o in index}, key=lambda w: lib.WATER_ORDER.index(w)
                if w in lib.WATER_ORDER else 9)
sel_waters = st.sidebar.multiselect("Тип воды", waters, default=waters)
flt = [o for o in index if o["water"] in sel_waters] or index

obj_labels = {f"{o['name']}  ·  {WATER_EMOJI.get(o['water'],'')} {o['water']}": o["id"] for o in flt}
obj_choice = st.sidebar.selectbox("Объект", list(obj_labels))
object_id = obj_labels[obj_choice]
obj = lib.get_object(object_id)

agg_ids = [a.id for a in obj.working_aggregates()]
agg_id = st.sidebar.selectbox("Агрегат", agg_ids)
agg = obj.aggregate(agg_id)
audit = lib.get_audit(object_id, agg_id)

ctx = Ctx(object_id=object_id, agg_id=agg_id, obj=obj, agg=agg,
          audit=audit, tariff=lib.tariff())

st.sidebar.markdown("---")
st.sidebar.caption(f"Ветка расчёта: **{obj.branch.value}**")
st.sidebar.caption(f"Тип насоса: **{audit.pump_kind}**")
st.sidebar.caption(f"Источник: {obj.source.split('/')[-1]}")

# ───────────────────────── Hero-хедер ─────────────────────────

_eta_ratio = (audit.regime.eta_unit / audit.regime.eta_nom) if audit.regime.eta_nom else 1.0
_eta_tone = "ok" if _eta_ratio >= 0.9 else ("warn" if _eta_ratio >= 0.78 else "bad")
ui.hero(
    f"{obj.name} · {agg_id}",
    f"Цифровой энергоаудит ППД · источник: {obj.source.split('/')[-1]}",
    [(f"{WATER_EMOJI.get(obj.water_type.value, '')} {obj.water_type.value} вода", ""),
     (f"ветка: {obj.branch.value}", ""),
     (f"насос: {audit.pump_kind}", ""),
     (f"КПД {fmt(audit.regime.eta_unit, 3)} / ном {fmt(audit.regime.eta_nom, 3)}", _eta_tone),
     (f"УРЭ {fmt(audit.sec_fact, 2)} кВт·ч/м³", "")])

# ───────────────────────── Вкладки (от общего к частному) ─────────────────────────

TABS = [
    ("📋 Обзор", overview),
    ("🗺️ Схема ППД", scheme),
    ("📉 Карта потерь", losses),
    ("📈 Рабочая точка", working_point),
    ("💡 Мероприятия", measures),
    ("🧩 Новый объект", new_object),
    ("🧮 Формулы", formulas),
    ("✅ Качество данных", quality),
]

for tab, (_, module) in zip(st.tabs([t for t, _ in TABS]), TABS):
    with tab:
        module.render(ctx)
