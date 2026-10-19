import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from tabs import losses


def test_loss_glossary_distinguishes_nominal_and_efficiency_losses():
    glossary = dict(losses._loss_glossary(["Номинальные", "Потери КПД"]))

    assert "даже при паспортном КПД" in glossary[losses.LOSS_LABELS["nominal"]]
    assert "сверх паспортного" in glossary[losses.LOSS_LABELS["efficiency"]]


def test_power_flow_belongs_to_loss_tab():
    assert callable(losses._power_flow)


def test_loss_labels_share_canonical_terms_and_preserve_unknown_names():
    from tabs.common import LOSS_LABELS, loss_label

    assert loss_label("Номинальные") == LOSS_LABELS["nominal"]
    assert loss_label("Номинальные потери НА") == LOSS_LABELS["nominal"]
    assert loss_label("Гидравлика насос→БГ") == LOSS_LABELS["hydraulic_bg"]
    assert loss_label("Штуцирование скважин") == LOSS_LABELS["choke"]
    assert loss_label("Неизвестная составляющая") == "Неизвестная составляющая"
