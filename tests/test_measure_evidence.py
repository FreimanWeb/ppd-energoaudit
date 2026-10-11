"""Связь расчётного мероприятия с зарегистрированной составляющей потерь."""

from ppd_audit.core.audit import run_pump_audit
from ppd_audit.measures import CATALOG, evaluate


def test_measure_evaluation_retains_registered_loss_basis():
    registered = next(item for item in CATALOG if item.id == "efficiency_recovery_scenario")
    result = evaluate(registered, run_pump_audit("kns25"))
    assert result.addresses == registered.addresses
