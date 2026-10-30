"""Общая типографика формул сохраняет вычисленные значения и подстановки."""

from ppd_audit.services.formula_view import formula_entries


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
