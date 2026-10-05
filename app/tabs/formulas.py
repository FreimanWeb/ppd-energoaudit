"""Формулы — drill-down: как получено каждое число (номер формулы методики)."""

from __future__ import annotations

import streamlit as st
import ui

from ppd_audit.services.formula_view import formula_entries
from tabs.common import Ctx, clean_nums, fmt


# Порядок показа — как в методике.
_ORDER = ["8", "11", "13", "14", "16", "17", "24", "25-26", "27", "29", "30", "44"]


def render(ctx: Ctx) -> None:
    st.subheader("Как получено каждое число — формулы методики")
    ui.provenance(("Расчёт по Методике", "ok"))
    st.caption("Формула → подстановка фактических величин → результат.")
    entries = formula_entries(ctx.audit.trace)
    for fid in _ORDER:
        t = entries.get(fid)
        if not t:
            continue
        with st.container(border=True):
            cL, cR = st.columns([3, 1])
            cL.markdown(f"**({fid}) {t['name']}**")
            cR.markdown(
                f"<div style='text-align:right;font-size:1.25em;color:#111827'>"
                f"<b>{fmt(t['value'], 4)}</b></div>",
                unsafe_allow_html=True,
            )
            if t["latex"]:
                st.latex(t["latex"])
            subst = t.get("subst", "")
            if t["subst_latex"] is None:  # символьная подстановка (напр. 25-26)
                st.caption(f"подстановка: {clean_nums(subst)} → {clean_nums(t['value'])}")
            else:
                st.latex(t["subst_latex"])
