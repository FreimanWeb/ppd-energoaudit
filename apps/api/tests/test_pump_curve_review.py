import json
import subprocess
import sys

import openpyxl
import pytest

from ppd_audit.config import project_root


@pytest.fixture
def workbook(tmp_path):
    path = tmp_path / "source.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Уравнения"
    sheet.append(["Характеристики насосов по приложению Д"])
    sheet.append([
        "Тип насоса",
        "Минимальная подача, м³/ч",
        "Максимальная подача, м³/ч",
        "Квадратичное уравнение H(Q)",
        "Квадратичное уравнение η(Q)",
        "aH",
        "bH",
        "cH",
        "aη",
        "bη",
        "cη",
    ])
    # Source row for ЦНС 40-1000-2: eta coefficients are in percent, not fractions.
    sheet.append([
        "ЦНС 40-1000-2",
        28,
        60,
        "H(Q)",
        "η(Q)",
        -0.10541667,
        5.503873,
        725.8529,
        -0.01041667,
        1.10049,
        22.411765,
    ])
    book.save(path)
    return path


def run_review(workbook, *args):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ppd_audit.verify.pump_curves",
            str(workbook),
            "--model",
            "ЦНС 40-1000-2",
            "--object",
            "kns97pren",
            "--aggregate",
            "НА-2 ПР",
            *args,
        ],
        cwd=project_root(),
        capture_output=True,
        text=True,
        check=False,
    )


def test_percent_efficiency_and_head_agree_with_existing_core(workbook):
    result = run_review(workbook, "--flows", "28", "40.25", "48", "60")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    point = report["points"][1]
    assert point["head_m"] == pytest.approx(776.602194308125, abs=1e-5)
    assert point["eta_fraction"] == pytest.approx(0.49830831058125, abs=1e-8)
    assert point["core_head_m"] == pytest.approx(point["head_m"])
    assert point["core_eta_fraction"] == pytest.approx(point["eta_fraction"])
    assert report["approval"] == "pending"
    assert report["current_regime"]["candidate_h_due_m"] == pytest.approx(point["head_m"])


def test_outside_domain_is_not_extrapolated(workbook):
    result = run_review(workbook, "--flows", "27.99", "28", "60", "60.01")
    assert result.returncode == 0, result.stderr
    points = json.loads(result.stdout)["points"]
    assert [point["status"] for point in points] == [
        "out_of_range",
        "within_source_range",
        "within_source_range",
        "out_of_range",
    ]
    for index in (0, 3):
        assert points[index]["head_m"] is None
        assert points[index]["eta_fraction"] is None


@pytest.mark.parametrize("flow", ["nan", "inf"])
def test_nonfinite_flow_is_rejected_without_report(workbook, flow):
    result = run_review(workbook, "--flows", flow)
    assert result.returncode == 2
    assert not result.stdout


def test_different_pump_model_cannot_be_applied_to_object(workbook):
    book = openpyxl.load_workbook(workbook)
    book["Уравнения"]["A3"] = "ЦНС 40-1000-1"
    book.save(workbook)
    result = run_review(workbook, "--model", "ЦНС 40-1000-1")
    assert result.returncode == 2
    assert not result.stdout


def test_review_does_not_modify_source_or_live_passport(workbook):
    passport = project_root() / "config/plants/kns97pren.yaml"
    original_source = workbook.read_bytes()
    original_passport = passport.read_bytes()
    result = run_review(workbook)
    assert result.returncode == 0, result.stderr
    assert workbook.read_bytes() == original_source
    assert passport.read_bytes() == original_passport
