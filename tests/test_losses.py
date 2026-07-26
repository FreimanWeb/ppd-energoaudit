import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from tabs import losses


def test_loss_glossary_distinguishes_nominal_and_efficiency_losses():
    glossary = dict(losses._loss_glossary(["Номинальные", "Потери КПД"]))

    assert "даже при паспортном КПД" in glossary["Номинальные"]
    assert "сверх паспортного" in glossary["Потери КПД"]


def test_power_flow_belongs_to_loss_tab():
    assert callable(losses._power_flow)
