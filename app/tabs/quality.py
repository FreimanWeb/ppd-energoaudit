"""✅ Качество данных — полнота режима + отчёт качества телеметрии (если есть)."""

from __future__ import annotations

import json

import streamlit as st

import lib
from tabs.common import Ctx, fmt


def render(ctx: Ctx) -> None:
    st.subheader("Качество и происхождение данных")
    st.write(f"**Источник:** {ctx.obj.source}")
    rm = ctx.agg.regime
    fields = {
        "ρ (плотность)": rm.rho, "p_вх": rm.p_in, "p_вых": rm.p_out, "p_БГ": rm.p_bg,
        "Q_сут": rm.q_day, "T (сут)": rm.t, "W (ЭЭ/сут)": rm.w,
        "P_эл": rm.p_electric, "T_год": rm.t_year}
    st.markdown("**Полнота режима:**")
    st.dataframe({"Параметр": list(fields),
                  "Значение": [fmt(v, 3) if v is not None else "— нет данных"
                               for v in fields.values()],
                  "Статус": ["✓" if v is not None else "—" for v in fields.values()]},
                 width="stretch", hide_index=True)

    # отчёт качества телеметрии (если есть, напр. ДНС-7с)
    qpath = lib._ROOT / "data" / "generated" / ctx.object_id / "quality_report.json"
    if qpath.exists():
        st.markdown("**Отчёт качества телеметрии:**")
        rep = json.loads(qpath.read_text(encoding="utf-8"))
        if rep.get("flags"):
            for fl in rep["flags"]:
                st.warning(fl)
        bal = rep.get("balances", {})
        if "sec_fact" in bal:
            st.write("Баланс/УРЭ:", bal.get("sec_fact"))
    else:
        st.caption("Для объекта используется инженерный «… расчет.xlsx» как эталон; "
                   "телеметрических рядов нет (квалификация — по полноте режима выше). "
                   "Телеметрия сейчас есть только у пилота ДНС-7с.")
