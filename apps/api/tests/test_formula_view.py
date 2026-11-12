"""Общая типографика формул сохраняет вычисленные значения и подстановки."""

from ppd_audit.services.formula_view import formula_entries, loss_equations


def test_enriches_canonical_formula_without_recalculating_trace():
    original = {
        "8": {
            "formula": "исходная формула",
            "subst": "(14.0−1.0)·1e6/(1130.0·9.81)",
            "value": 1172.81,
        }
    }
    result = formula_entries(original)
    assert result["8"]["latex"].startswith(r"H_{\text{ф}}=\dfrac")
    assert result["8"]["name"] == "Фактический напор, м"
    assert r"\cdot 10^{6}" in result["8"]["subst_latex"]
    assert result["8"]["value"] == original["8"]["value"]
    assert original["8"] == {
        "formula": "исходная формула",
        "subst": "(14.0−1.0)·1e6/(1130.0·9.81)",
        "value": 1172.81,
    }


def test_symbolic_substitution_stays_plain_and_unknown_formula_keeps_trace():
    result = formula_entries({
        "25-26": {"subst": "β = Kз", "value": 0.9},
        "99": {"formula": "custom", "value": 0},
    })
    assert result["25-26"]["subst_latex"] is None
    assert result["99"]["latex"] is None
    assert result["99"]["formula"] == "custom"
    assert result["99"]["value"] == 0


def test_loss_decimal_comma_does_not_escape_tex_unit_spacing():
    result = loss_equations("Q·(p_вых−p_БГ)/3,6", "120·(10−1)/3,6", 300)
    numeric = result["substitution_latex"]
    assert r"3{,}6" in numeric
    assert numeric.endswith(r"\,\text{кВт}")
    assert r"\{,}" not in numeric


def test_loss_typography_distinguishes_unknown_power_from_zero():
    unknown = loss_equations("P_эл·(1−η_ПЧ)", "529·(1−—)", None)
    zero = loss_equations("P_эл·(1−η_ПЧ)", "529·(1−1)", 0)
    assert r"\text{нет данных}" in unknown["substitution_latex"]
    assert " = " not in unknown["substitution_latex"]
    assert r"= 0\,\text{кВт}" in zero["substitution_latex"]


def test_loss_scientific_notation_keeps_sign_and_exponent():
    result = loss_equations("Q·(p_вых−p_БГ)/3,6", "-2e-07", -2e-7)
    numeric = result["substitution_latex"]
    assert numeric.startswith(r"-2\cdot 10^{-7}")
    assert r"= -2\cdot 10^{-7}" in numeric
    assert "e-" not in numeric


def test_loss_sum_explanation_is_not_interpreted_as_numeric_math():
    result = loss_equations("Σ Q_i·Δp_i/3,6", "Сумма сопротивлений участков", 100)
    assert result["substitution_latex"] is None
