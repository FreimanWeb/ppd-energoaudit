import pytest
from pydantic import ValidationError

from ppd_audit.core import curves
from ppd_audit.core.audit import audit_aggregate
from ppd_audit.spec import AggregateSpec, MotorSpec, PumpSpec, RegimeMeasurement


def _pump(**updates):
    values = {
        "model": "CONTROL-pump",
        "n_rpm": 3000,
        "q_nom": 40,
        "h_nom": 1000,
        "eta_nom": 0.7,
        "curve_qh": [[20, 1200], [40, 1000], [60, 600]],
        "curve_qeta": [[20, 0.4], [40, 0.7], [60, 0.6]],
        "curve_source": {
            "kind": "engineering",
            "reference": "Synthetic control input",
            "model": "CONTROL-pump",
            "speed_rpm": 3000,
            "verified": False,
        },
    }
    values.update(updates)
    return PumpSpec(**values)


def _audit(pump, q=40):
    return audit_aggregate(
        AggregateSpec(
            id="A",
            pump=pump,
            motor=MotorSpec(p_nom=300, eta_nom=0.9),
            regime=RegimeMeasurement(rho=1000, p_in=1, p_out=10, p_bg=9, q_fact=q, p_electric=200),
        )
    )


@pytest.mark.parametrize("q", [19.99, 60.01])
def test_head_curve_does_not_extrapolate(q):
    assert curves.head_due(q, _pump().curve_qh) is None


@pytest.mark.parametrize("q", [19.99, 60.01])
def test_efficiency_curve_does_not_extrapolate(q):
    assert curves.eta_due(q, _pump().curve_qeta) is None


@pytest.mark.parametrize(("q", "head", "eta"), [(20, 1200, 0.4), (60, 600, 0.6)])
def test_curve_endpoints_are_usable(q, head, eta):
    pump = _pump()
    assert curves.head_due(q, pump.curve_qh) == pytest.approx(head)
    assert curves.eta_due(q, pump.curve_qeta) == pytest.approx(eta)


def test_kns_evaluates_efficiency_characteristic_at_actual_flow():
    audit = _audit(_pump())
    assert audit.trace["30"]["value"] == pytest.approx(0.7)
    assert audit.eta_pump_due == pytest.approx(0.7)
    assert audit.characteristic.origin == "engineering"
    assert audit.characteristic.verified is False
    # Reference Q-eta must not silently replace the nominal passport efficiency.
    assert audit.regime.eta_nom == pytest.approx(0.7 * 0.9)


@pytest.mark.parametrize(
    "source",
    [
        {"kind": "engineering", "model": "another-pump", "speed_rpm": 3000},
        {"kind": "engineering", "model": "CONTROL-pump", "speed_rpm": 1500},
    ],
)
def test_incompatible_characteristic_is_not_used_for_due_values(source):
    audit = _audit(_pump(curve_source=source))
    assert audit.h_due is None
    assert audit.eta_pump_due is None


def test_out_of_range_kns_does_not_fall_back_to_manual_due_values():
    pump = _pump()
    spec = _audit(pump).spec.model_copy(
        update={
            "h_pump_due": 1000,
            "eta_pump_due": 0.7,
            "regime": RegimeMeasurement(
                rho=1000, p_in=1, p_out=10, p_bg=9, q_fact=65, p_electric=300
            ),
        }
    )
    audit = audit_aggregate(spec)
    assert audit.h_due is None
    assert audit.eta_pump_due is None


def test_nonphysical_efficiency_fit_is_not_clipped_or_used():
    assert curves.eta_due(1.5, [[0, 0.1], [1, 1], [2, 1]]) is None


@pytest.mark.parametrize(
    "points",
    [
        [[20, 40], [40, 70], [60, 60]],
        [[20, 0.4], [20, 0.7], [60, 0.6]],
        [[20, 0.4], [40, float("nan")], [60, 0.6]],
    ],
)
def test_invalid_efficiency_data_is_rejected(points):
    with pytest.raises(ValidationError):
        _pump(curve_qeta=points)


def test_persisted_curve_binding_still_blocks_another_pump(tmp_path):
    import json
    from datetime import datetime

    from ppd_audit.db import AuditDatabase
    from ppd_audit.services.telemetry_audit import object_from_database

    database = AuditDatabase(tmp_path / "curves.sqlite")
    database.migrate()
    database.upsert_plant("test", "Test", "QA", "пресная", "кнс")
    database.upsert_aggregate("test", "A", "работа")
    stamp = datetime(2026, 1, 1)
    pump = _pump(curve_source={"kind": "engineering", "model": "another-pump"})
    database.add_passport(
        "test",
        "A",
        valid_from=stamp,
        pump_model=pump.model,
        pump_kind=pump.kind.value,
        pump_q_nom=40,
        pump_h_nom=1000,
        pump_eta_nom=0.7,
        motor_model="Control",
        motor_p_nom=300,
        motor_eta_nom=0.9,
        pump_curve_qh_json=json.dumps(pump.curve_qh),
        pump_curve_qeta_json=json.dumps(pump.curve_qeta),
        pump_curve_source_json=pump.curve_source.model_dump_json(),
    )
    restored = object_from_database(database, "test", stamp).aggregate("A")
    assert _audit(restored.pump).h_due is None
