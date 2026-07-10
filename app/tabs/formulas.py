"""🧮 Формулы — drill-down: как получено каждое число (номер формулы методики)."""

from __future__ import annotations

import re

import streamlit as st

from tabs.common import Ctx, clean_nums, fmt

# Формулы методики в LaTeX (KaTeX, кириллица в \text{}).
_FORMULA_LATEX = {
    "8":  r"H_{\text{ф}}=\dfrac{(p_{\text{вых}}-p_{\text{вх}})\cdot 10^{6}}{\rho\,g}",
    "11": r"P_{\text{гидр}}=\dfrac{(p_{\text{вых}}-p_{\text{вх}})\cdot Q}{3{,}6}",
    "13": r"\eta_{\text{НА}}=\dfrac{P_{\text{гидр}}}{P_{\text{эл}}}",
    "14": r"\eta_{\text{ном}}=\eta_{\text{ЭД.ном}}\cdot\eta_{\text{нас.ном}}\cdot\eta_{\text{тр}}",
    "16": r"\text{УРЭ}_{\text{ф}}=\dfrac{W}{Q_{\text{сут}}}",
    "17": r"\text{УРЭ}_{\text{р}}=\dfrac{p_{\text{вых}}-p_{\text{вх}}}{3{,}6\,\eta_{\text{ном}}}",
    "24": r"K_{\text{з}}=\dfrac{P_{\text{эл}}}{P_{\text{ном}}/\eta_{\text{ЭД.ном}}}",
    "25-26": r"\eta_{\text{эд.р}}=\dfrac{1}{1+\left(\tfrac{1}{\eta_{\text{ЭД.ном}}}-1\right)\beta}",
    "27": r"\eta_{\text{нас}}=\dfrac{\eta_{\text{НА}}}{\eta_{\text{эд.р}}\cdot\eta_{\text{пч}}\cdot\eta_{\text{ред}}}",
    "29": r"H_{\text{д}}=aQ^{2}+bQ+c",
    "30": r"\eta_{\text{д}}=uQ^{2}+vQ+w",
    "44": r"\Delta W_{\text{кпд}}=Q_{\text{год}}\,(\text{УРЭ}_{\text{ф}}-\text{УРЭ}_{\text{р}})",
}
_FORMULA_NAME = {
    "8": "Фактический напор, м", "11": "Гидравлическая мощность, кВт",
    "13": "КПД насосной установки (факт)", "14": "Номинальный КПД",
    "16": "УРЭ фактический, кВт·ч/м³", "17": "УРЭ расчётный, кВт·ч/м³",
    "24": "Коэффициент загрузки ЭД", "25-26": "КПД ЭД при недогрузке",
    "27": "КПД насоса", "29": "Должный напор (паспортная кривая), м",
    "30": "Должный КПД насоса, о.е.", "44": "Годовые потери по КПД, кВт·ч/год",
}
# Порядок показа — как в методике.
_ORDER = ["8", "11", "13", "14", "16", "17", "24", "25-26", "27", "29", "30", "44"]


def _subst_to_latex(s: str) -> str:
    """Числовая подстановка → LaTeX-выражение."""
    return (clean_nums(s).replace("1e6", r"\cdot 10^{6}")
            .replace("·", r"\cdot ").replace("−", "-"))


def render(ctx: Ctx) -> None:
    st.subheader("Как получено каждое число — формулы методики")
    st.caption("Символьная формула (Методика, разд. 8) → подстановка фактических величин → "
               "результат. Число в скобках — номер формулы методики. Полная карта "
               "«формула → код → тест» — docs/formula_map.md.")
    for fid in _ORDER:
        t = ctx.audit.trace.get(fid)
        if not t:
            continue
        with st.container(border=True):
            cL, cR = st.columns([3, 1])
            cL.markdown(f"**({fid}) {_FORMULA_NAME.get(fid, '')}**")
            cR.markdown(
                f"<div style='text-align:right;font-size:1.25em;color:#2f6098'>"
                f"<b>{fmt(t['value'], 4)}</b></div>", unsafe_allow_html=True)
            if fid in _FORMULA_LATEX:
                st.latex(_FORMULA_LATEX[fid])
            subst = t.get("subst", "")
            if re.search(r"[А-Яа-яα-ω]", subst):     # символьная подстановка (напр. 25-26)
                st.caption(f"подстановка: {clean_nums(subst)} → {clean_nums(t['value'])}")
            else:
                st.latex(_subst_to_latex(subst) + " = " + clean_nums(t["value"]))
