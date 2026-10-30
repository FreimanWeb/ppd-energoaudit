from ppd_audit.core.audit import AuditResult
from ppd_audit.services.audit import run_energy_audit
from ppd_audit.spec import load_object_spec


def test_run_energy_audit_returns_core_result():
    spec = load_object_spec("dns7s")

    result = run_energy_audit(spec, "Н-4")

    assert isinstance(result, AuditResult)
    assert result.aggregate_id == "Н-4"
    assert result.sec_fact > 0
    assert result.regime.eta_unit > 0
    assert "16" in result.trace
