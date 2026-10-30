"""Общая типографика формул для HTTP API; без пересчёта значений."""

import re


# Формулы методики в LaTeX (KaTeX, кириллица в \text{}).
FORMULA_LATEX = {
    "8": r"H_{\text{ф}}=\dfrac{(p_{\text{вых}}-p_{\text{вх}})\cdot 10^{6}}{\rho\,g}",
    "11": r"P_{\text{гидр}}=\dfrac{(p_{\text{вых}}-p_{\text{вх}})\cdot Q}{3{,}6}",
    "13": r"\eta_{\text{НА}}=\dfrac{P_{\text{гидр}}}{P_{\text{эл}}}",
    "14": r"\eta_{\text{ном}}=\eta_{\text{ЭД.ном}}\cdot\eta_{\text{нас.ном}}\cdot\eta_{\text{тр}}",
    "16": r"\text{УРЭ}_{\text{ф}}=\dfrac{W}{Q_{\text{сут}}}",
    "17": r"\text{УРЭ}_{\text{р}}=\dfrac{p_{\text{вых}}-p_{\text{вх}}}{3{,}6\,\eta_{\text{ном}}}",
    "24": r"K_{\text{з}}=\dfrac{P_{\text{эл}}}{P_{\text{ном}}/\eta_{\text{ЭД.ном}}}",
    "25-26": r"\eta_{\text{эд.р}}=\dfrac{1}{1+\left(\tfrac{1}{\eta_{\text{ЭД.ном}}}-1\right)\beta}",
    "27": (
        r"\eta_{\text{нас}}=\dfrac{\eta_{\text{НА}}}"
        r"{\eta_{\text{эд.р}}\cdot\eta_{\text{пч}}\cdot\eta_{\text{ред}}}"
    ),
    "29": r"H_{\text{д}}=aQ^{2}+bQ+c",
    "30": r"\eta_{\text{д}}=uQ^{2}+vQ+w",
    "44": r"\Delta W_{\text{кпд}}=Q_{\text{год}}\,(\text{УРЭ}_{\text{ф}}-\text{УРЭ}_{\text{р}})",
}
FORMULA_NAME = {
    "8": "Фактический напор, м",
    "11": "Гидравлическая мощность, кВт",
    "13": "КПД насосной установки (факт)",
    "14": "Номинальный КПД",
    "16": "УРЭ фактический, кВт·ч/м³",
    "17": "УРЭ расчётный, кВт·ч/м³",
    "24": "Коэффициент загрузки ЭД",
    "25-26": "КПД ЭД при недогрузке",
    "27": "КПД насоса",
    "29": "Должный напор (паспортная кривая), м",
    "30": "Должный КПД насоса, о.е.",
    "44": "Годовые потери по КПД, кВт·ч/год",
}


def _clean_numbers(value) -> str:
    return re.sub(r"-?\d+\.\d+", lambda m: f"{float(m.group()):.4g}", str(value))


def formula_entries(trace: dict) -> dict:
    """Дополнить исходный trace метаданными отображения, сохранив исходные поля."""
    result = {}
    for fid, entry in trace.items():
        subst = str(entry.get("subst", ""))
        symbolic = re.search(r"[А-Яа-яα-ω]", subst)
        numeric = (
            _clean_numbers(subst)
            .replace("1e6", r"\cdot 10^{6}")
            .replace("·", r"\cdot ")
            .replace("−", "-")
        )
        result[fid] = {
            **entry,
            "name": FORMULA_NAME.get(fid, "Расчётная формула"),
            "latex": FORMULA_LATEX.get(fid),
            "subst_latex": None
            if symbolic or not subst
            else numeric + " = " + _clean_numbers(entry.get("value")),
        }
    return result
