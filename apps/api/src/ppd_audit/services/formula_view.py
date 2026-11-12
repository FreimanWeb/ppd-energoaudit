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
    "44": r"\Delta W_{\text{кпд}}=Q_{\text{год}}\,(\text{УРЭ}_{\text{реж}}-\text{УРЭ}_{\text{р}})",
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


# Исходная запись остаётся в трассировке; это только математическое представление.
LOSS_FORMULA_LATEX = {
    "P_эл·(1−η_ПЧ)": r"\Delta P_{\text{ПЧ}}=P_{\text{эл}}\,(1-\eta_{\text{ПЧ}})",
    "P_послеПЧ·(1−η_ЭД.расч)": (
        r"\Delta P_{\text{ЭД}}=P_{\text{после ПЧ}}\,(1-\eta_{\text{ЭД.расч}})"
    ),
    "P_послеЭД·(1−η_передачи)": (
        r"\Delta P_{\text{передачи}}=P_{\text{после ЭД}}\,(1-\eta_{\text{передачи}})"
    ),
    "P_навалу−Q·(p_вых−p_вх)/3,6": (
        r"\Delta P_{\text{насоса}}=P_{\text{на валу}}"
        r"-\frac{Q\,(p_{\text{вых}}-p_{\text{вх}})}{3{,}6}"
    ),
    "Q·(p_вых−p_БГ)/3,6": (
        r"\Delta P_{\text{насос–БГ}}=\frac{Q\,(p_{\text{вых}}-p_{\text{БГ}})}{3{,}6}"
    ),
    "P_БГ·(1/η_ном−1)": (
        r"\Delta P_{\text{ном}}=P_{\text{БГ}}\left(\frac{1}{\eta_{\text{ном}}}-1\right)"
    ),
    "P_гидр·(1/η_ном−1)": (
        r"\Delta P_{\text{ном}}=P_{\text{гидр}}\left(\frac{1}{\eta_{\text{ном}}}-1\right)"
    ),
    "P_эл−P_гидр/η_ном": (
        r"\Delta P_{\eta}=P_{\text{эл}}-\frac{P_{\text{гидр}}}{\eta_{\text{ном}}}"
    ),
    "Q·(p_вых−p_БГ)/3,6·(1/η_ном−1)": (
        r"\Delta P_{\text{напор}}=\frac{Q\,(p_{\text{вых}}-p_{\text{БГ}})}{3{,}6}"
        r"\left(\frac{1}{\eta_{\text{ном}}}-1\right)"
    ),
    "P_гидр·(1/(η_д·η_ЭД.ном)−1/η_ном)": (
        r"\Delta P_Q=P_{\text{гидр}}"
        r"\left(\frac{1}{\eta_{\text{д}}\eta_{\text{ЭД.ном}}}"
        r"-\frac{1}{\eta_{\text{ном}}}\right)"
    ),
    "P_гидр/η_ЭД.ном·(1/η_нас−1/η_д.в)": (
        r"\Delta P_{\text{износ}}=\frac{P_{\text{гидр}}}{\eta_{\text{ЭД.ном}}}"
        r"\left(\frac{1}{\eta_{\text{нас}}}-\frac{1}{\eta_{\text{д.в}}}\right)"
    ),
    "P_эл−P_гидр/(η_нас·η_ЭД.ном)": (
        r"\Delta P_{\text{загрузка ЭД}}=P_{\text{эл}}"
        r"-\frac{P_{\text{гидр}}}{\eta_{\text{нас}}\eta_{\text{ЭД.ном}}}"
    ),
    "P_гидр/η_ЭД.ном·(1/η_д.в−1/η_д)": (
        r"\Delta P_{\text{вязкость}}=\frac{P_{\text{гидр}}}{\eta_{\text{ЭД.ном}}}"
        r"\left(\frac{1}{\eta_{\text{д.в}}}-\frac{1}{\eta_{\text{д}}}\right)"
    ),
    "Σ Q_i·Δp_i/3,6": r"\sum_i \frac{Q_i\,\Delta p_i}{3{,}6}",
    "ΔP_i=Q_i·Δp_Darcy–Weisbach/3,6": (
        r"\Delta P_i=\frac{Q_i\,\Delta p_{\text{Darcy–Weisbach}}}{3{,}6}"
    ),
    "ΔP_i=Q_i·Δp_i/3,6": r"\Delta P_i=\frac{Q_i\,\Delta p_i}{3{,}6}",
}


def loss_equations(formula: str, substitution: str, power: float | None) -> dict:
    """Оформить выражение и числовую подстановку без пересчёта результата."""
    numeric = None
    if re.fullmatch(r"[\d.eE+\-−·*/(),\s—]+", substitution):
        numeric = substitution
        if power is not None:
            numeric += f" = {power:g}"
        numeric = re.sub(
            r"(\d+(?:\.\d+)?)[eE]([+-]?\d+)",
            lambda match: rf"{match[1]}\cdot 10^{{{int(match[2])}}}",
            numeric,
        )
        numeric = (
            numeric
            .replace("·", r"\cdot ")
            .replace("−", "-")
            .replace("—", r"\text{нет данных}")
            .replace(",", "{,}")
        )
        if power is not None:
            numeric += r"\,\text{кВт}"
    return {"formula_latex": LOSS_FORMULA_LATEX[formula], "substitution_latex": numeric}
