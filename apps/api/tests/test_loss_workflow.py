"""Consumer boundaries: scoped detail, provenance, history and no telemetry overwrite."""

import json
from datetime import datetime
from importlib import import_module

import pytest
from fastapi.testclient import TestClient

from ppd_audit.db import AuditDatabase


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    db = AuditDatabase(tmp_path / "workflow.sqlite")
    db.migrate()
    db.upsert_plant("workflow", "Проверка", "НГДУ", "пресная", "кнс", default_density=1000)
    for code in ("A", "B"):
        db.upsert_aggregate("workflow", code, "работа")
        db.add_passport(
            "workflow",
            code,
            valid_from=datetime(2026, 1, 1),
            pump_model="ЦНС36",
            pump_kind="центробежный",
            pump_q_nom=36,
            pump_h_nom=1000,
            pump_eta_nom=0.8,
            motor_model="ЭД",
            motor_p_nom=200,
            motor_eta_nom=0.9,
            transmission_eff=0.98,
            vfd=True,
        )
    for metric, value, unit in [
        ("p_in", 1, "МПа"),
        ("p_out", 10, "МПа"),
        ("flow_rate", 36, "м³/ч"),
        ("power", 180, "кВт"),
        ("density", 1000, "кг/м³"),
    ]:
        db.add_measurement("workflow", "A", datetime(2026, 1, 2, 12), metric, value, unit)
    db.add_measurement("workflow", None, datetime(2026, 1, 2, 12), "p_bg", 9, "МПа")
    main = import_module("ppd_audit.api.main")
    monkeypatch.setattr(main, "_database", lambda: db)
    monitoring_routes = import_module("ppd_audit.api.monitoring_routes")
    monkeypatch.setattr(monitoring_routes, "_database", lambda: db)
    return TestClient(main.app), db


BASE = "/objects/workflow/aggregates/A"
CONTEXT = {"source": "telemetry", "day": "2026-01-02", "timestamp": "2026-01-02T12:00:00"}


def test_hall_breakdown_balances_without_downstream_network(workflow):
    client, _ = workflow
    response = client.post(BASE + "/loss-detail", json={**CONTEXT, "key": "hall"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_kw"] == pytest.approx(100)
    assert data["input_kw"] == pytest.approx(180)
    assert data["output_kw"] == pytest.approx(80)
    assert sum(c["power_kw"] for c in data["components"]) == pytest.approx(100)
    hydraulic = next(c for c in data["components"] if c["key"] == "hydraulic_bg_loss")
    assert hydraulic["power_kw"] == pytest.approx(10)
    assert hydraulic["origin"] == "calculated"
    assert data["annual_kwh"] == pytest.approx(100 * data["annual_runtime_hours"])


def test_causal_overview_balances_without_counting_efficiency_factors_twice(workflow):
    client, _ = workflow
    response = client.post(BASE + "/loss-detail", json={**CONTEXT, "key": "hall_causal"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["input_kw"] == pytest.approx(180)
    assert data["output_kw"] == pytest.approx(80)
    assert data["total_kw"] == pytest.approx(100)
    assert sum(c["power_kw"] for c in data["components"]) == pytest.approx(100)
    assert {c["key"] for c in data["components"]} == {
        "nominal_loss",
        "efficiency_loss",
        "throttle_loss",
        "hydraulic_bg_loss",
    }
    factors = client.post(BASE + "/loss-detail", json={**CONTEXT, "key": "efficiency_causes"})
    assert factors.status_code == 200, factors.text
    detail = factors.json()
    deviation = next(c["power_kw"] for c in data["components"] if c["key"] == "efficiency_loss")
    assert detail["total_kw"] == pytest.approx(deviation)
    assert all(c["power_kw"] is None for c in detail["components"])
    assert detail["unallocated_kw"] == pytest.approx(deviation)


def test_causal_overview_retains_known_balance_when_nominal_efficiency_is_cleared(workflow):
    client, _ = workflow
    revision = client.get(BASE + "/equipment-journal").json()["revision"]
    saved = client.post(
        BASE + "/equipment-journal",
        json={
            "component": "pump",
            "effective_at": "2026-01-02T10:00:00",
            "expected_revision": revision,
            "changes": {"pump.eta_nom": None},
            "reason": "passport",
            "evidence": "documented",
            "source": "КПД не указан в паспорте",
            "author": "Инженер",
        },
    )
    assert saved.status_code == 200, saved.text
    response = client.post(BASE + "/loss-detail", json={**CONTEXT, "key": "hall_causal"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_kw"] == pytest.approx(100)
    assert data["status"] == "partial"
    assert data["unallocated_kw"] == pytest.approx(90)
    parts = {c["key"]: c["power_kw"] for c in data["components"]}
    assert parts["hydraulic_bg_loss"] == pytest.approx(10)
    assert all(parts[key] is None for key in ("nominal_loss", "efficiency_loss", "throttle_loss"))


def test_pumping_causal_boundary_stops_at_pump_and_preserves_factor_balance():
    from ppd_audit.core.audit import audit_aggregate
    from ppd_audit.services.loss_details import build_loss_detail
    from ppd_audit.spec import AggregateSpec, Branch, MotorSpec, PumpSpec, RegimeMeasurement

    audit = audit_aggregate(
        AggregateSpec(
            id="A",
            pump=PumpSpec(eta_nom=0.8),
            motor=MotorSpec(p_nom=200, eta_nom=0.9),
            regime=RegimeMeasurement(rho=1000, p_in=1, p_out=10, q_fact=36, p_electric=180),
        ),
        branch=Branch("перекачка"),
    )
    overview = build_loss_detail(audit, "hall_causal", tariff=5)
    assert overview["output_kw"] == pytest.approx(90)
    assert overview["total_kw"] == pytest.approx(90)
    assert {c["key"] for c in overview["components"]} == {"nominal_loss", "efficiency_loss"}
    assert sum(c["power_kw"] for c in overview["components"]) == pytest.approx(90)
    factors = build_loss_detail(audit, "efficiency_causes", tariff=5)
    assert factors["total_kw"] == pytest.approx(audit.decomposition.dp_efficiency)
    assert sum(c["power_kw"] for c in factors["components"]) == pytest.approx(factors["total_kw"])
    assert factors["balance_residual_kw"] == pytest.approx(0, abs=1e-9)


def test_equipment_journal_rejects_stale_edit_and_recalculates_only_its_period(workflow):
    client, _ = workflow
    initial = client.get(BASE + "/equipment-journal").json()
    payload = {
        "component": "transmission",
        "effective_at": "2026-01-02T00:00:00",
        "expected_revision": initial["revision"],
        "changes": {"transmission.efficiency": 0.96},
        "reason": "passport",
        "evidence": "documented",
        "source": "Паспорт передачи №123",
        "author": "Инженер",
    }
    saved = client.post(BASE + "/equipment-journal", json=payload)
    assert saved.status_code == 200, saved.text
    historical = client.get(BASE + "/equipment", params={"at": "2026-01-01T12:00:00"}).json()
    assert historical["equipment"]["transmission"]["efficiency"] == 0.98
    assert client.post(BASE + "/equipment-journal", json=payload).status_code == 409
    detail = client.post(BASE + "/loss-detail", json={**CONTEXT, "key": "hall"}).json()
    transmission = next(c for c in detail["components"] if c["key"] == "transmission_loss")
    assert transmission["power_kw"] == pytest.approx(180 * 0.97 * 0.9 * 0.04)


def _seed_archived_measurement(db, measured_at, regime):
    with db._connection() as connection:
        aggregate_id = db._aggregate_id(connection, "workflow", "A", None)
        cursor = connection.execute(
            """INSERT INTO manual_measurements
               (aggregate_id, measured_at, regime_json, source, comment, author, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                aggregate_id,
                measured_at,
                json.dumps({"measured_at": measured_at[:10], **regime}),
                "Архивный протокол",
                "Существовавшая запись",
                "Инженер",
                "2026-01-10T12:00:00+00:00",
            ),
        )
        return cursor.lastrowid


def test_archived_measurement_remains_explicit_scoped_and_separate_from_telemetry(workflow):
    client, db = workflow
    original = db.measurements("workflow", "A")
    measurement_id = _seed_archived_measurement(
        db,
        "2026-01-03T10:30:00",
        {
            "rho": 1000,
            "p_in": 1,
            "p_out": 10,
            "p_bg": 8,
            "q_fact": 36,
            "p_electric": 150,
            "t_year": 4800,
        },
    )
    archive = client.get(BASE + "/manual-measurements").json()["items"]
    assert (
        next(row for row in archive if row["id"] == measurement_id)["regime"]["p_electric"] == 150
    )
    context = {"source": "field_trip", "measurement_id": measurement_id, "key": "hall"}
    detail = client.post(BASE + "/loss-detail", json=context)
    assert detail.status_code == 200, detail.text
    assert detail.json()["input_kw"] == pytest.approx(150)
    assert detail.json()["output_kw"] == pytest.approx(70)
    assert detail.json()["annual_kwh"] == pytest.approx(80 * 4800)
    foreign = client.post("/objects/workflow/aggregates/B/loss-detail", json=context)
    assert foreign.status_code in (400, 404)
    assert db.measurements("workflow", "A") == original


def test_requirements_available_without_telemetry_and_no_zero_as_missing(workflow):
    client, _ = workflow
    response = client.get(
        "/objects/workflow/aggregates/B/data-requirements", params={"at": CONTEXT["timestamp"]}
    )
    assert response.status_code == 200, response.text
    requirements = {r["key"]: r for r in response.json()["requirements"]}
    assert requirements["regime.p_bg"]["status"] == "missing"
    assert requirements["pump.curve_qh"]["status"] == "missing"
    assert requirements["transmission.efficiency"]["status"] == "pending_confirmation"


def test_missing_motor_efficiency_keeps_total_and_explicit_unallocated_part(workflow):
    client, _ = workflow
    response = client.get(BASE + "/equipment", params={"at": CONTEXT["timestamp"]})
    assert response.status_code == 200, response.text
    equipment = response.json()["equipment"]
    equipment["motor"]["eta_nom"] = None
    response = client.post(
        BASE + "/loss-detail",
        json={
            **CONTEXT,
            "key": "hall",
            "equipment_override": equipment,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "partial"
    assert data["total_kw"] == pytest.approx(100)
    unknown = {c["key"] for c in data["components"] if c["power_kw"] is None}
    assert unknown == {"motor_chain_loss", "transmission_loss", "pump_loss"}
    assert data["unallocated_kw"] == pytest.approx(84.6)
    assert sum(c["power_kw"] or 0 for c in data["components"]) + data[
        "unallocated_kw"
    ] == pytest.approx(100)


def test_temporary_equipment_changes_recalculate_without_publishing(workflow):
    client, _ = workflow
    initial = client.get(BASE + "/equipment", params={"at": CONTEXT["timestamp"]})
    assert initial.status_code == 200, initial.text
    initial = initial.json()
    equipment = initial["equipment"]
    equipment["transmission"]["efficiency"] = 0.95
    result = client.post(
        BASE + "/loss-detail",
        json={
            **CONTEXT,
            "key": "transmission_loss",
            "equipment_override": equipment,
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["total_kw"] == pytest.approx(180 * 0.97 * 0.9 * 0.05)
    unchanged = client.get(BASE + "/equipment", params={"at": CONTEXT["timestamp"]}).json()
    assert unchanged["revision"] == initial["revision"]
    assert unchanged["equipment"]["transmission"]["efficiency"] == 0.98


def test_zero_pressure_and_zero_annual_runtime_in_archive_are_not_missing(workflow):
    client, db = workflow
    measurement_id = _seed_archived_measurement(
        db,
        "2026-01-03T12:00:00",
        {
            "rho": 1000,
            "p_in": 0,
            "p_out": 9,
            "p_bg": 8,
            "q_fact": 36,
            "p_electric": 180,
            "t_year": 0,
        },
    )
    request = {"source": "field_trip", "measurement_id": measurement_id}
    rows = client.post(BASE + "/data-requirements", json=request)
    assert rows.status_code == 200, rows.text
    rows = {r["key"]: r for r in rows.json()["requirements"]}
    assert rows["regime.p_in"]["status"] == "ready"
    assert rows["regime.p_in"]["value"] == 0
    assert rows["regime.t_year"]["status"] == "ready"
    assert rows["regime.t_year"]["value"] == 0
    detail = client.post(BASE + "/loss-detail", json={**request, "key": "hall"}).json()
    assert detail["total_kw"] == pytest.approx(100)
    assert detail["annual_kwh"] == 0


def test_incompatible_equipment_allocation_does_not_hide_measured_total_or_signed_deviation():
    from ppd_audit.core.audit import audit_aggregate
    from ppd_audit.services.loss_details import build_loss_detail
    from ppd_audit.spec import AggregateSpec, MotorSpec, PumpSpec, RegimeMeasurement

    audit = audit_aggregate(
        AggregateSpec(
            id="A",
            pump=PumpSpec(eta_nom=0.8),
            motor=MotorSpec(p_nom=200, eta_nom=0.4),
            regime=RegimeMeasurement(rho=1000, p_in=1, p_out=10, p_bg=9, q_fact=36, p_electric=180),
        )
    )
    physical = build_loss_detail(audit, "hall", tariff=5)
    assert physical["total_kw"] == pytest.approx(100)
    assert physical["status"] == "partial"
    assert physical["unallocated_kw"] == pytest.approx(90)
    causal = build_loss_detail(audit, "efficiency_loss", tariff=5)
    assert causal["total_kw"] == pytest.approx(audit.decomposition.dp_efficiency)
    assert causal["total_kw"] < 0
    overview = build_loss_detail(audit, "hall_causal", tariff=5)
    assert overview["total_kw"] == pytest.approx(100)
    assert sum(c["power_kw"] for c in overview["components"]) == pytest.approx(100)
    deviation = next(c for c in overview["components"] if c["key"] == "efficiency_loss")
    assert deviation["power_kw"] == pytest.approx(causal["total_kw"])
    assert deviation["share_pct"] < 0


@pytest.mark.parametrize(
    "group,field,value",
    [
        ("pump", "eta_nom", 90),
        ("motor", "eta_nom", 0),
        ("transmission", "efficiency", 1.1),
        ("motor", "p_nom", -100),
    ],
)
def test_equipment_domain_validation_applies_to_publish_and_scenario(workflow, group, field, value):
    client, _ = workflow
    initial = client.get(BASE + "/equipment", params={"at": CONTEXT["timestamp"]}).json()
    equipment = initial["equipment"]
    equipment[group][field] = value
    publish = client.post(
        BASE + "/equipment-journal",
        json={
            "component": group,
            "effective_at": CONTEXT["timestamp"],
            "expected_revision": initial["revision"],
            "changes": {f"{group}.{field}": value},
            "reason": "passport",
            "evidence": "documented",
            "source": "Паспорт",
            "author": "Инженер",
        },
    )
    assert publish.status_code == 422, publish.text
    scenario = client.post(
        BASE + "/loss-detail",
        json={
            **CONTEXT,
            "key": "hall",
            "equipment_override": equipment,
        },
    )
    assert scenario.status_code == 422, scenario.text
    assert client.get(BASE + "/equipment").json()["revision"] == initial["revision"]


def test_removed_full_write_endpoints_cannot_create_manual_records(workflow):
    client, _ = workflow
    assert client.post(BASE + "/manual-measurements", json={}).status_code == 405
    assert client.post(BASE + "/equipment", json={}).status_code == 405
    assert client.get(BASE + "/manual-measurements").json()["items"] == []


def test_inherited_equipment_parameter_keeps_its_own_source(workflow):
    client, _ = workflow
    _journal_change(
        client,
        "motor",
        "2026-01-02T00:00:00",
        {"motor.eta_nom": 0.9},
        source="Паспорт электродвигателя",
    )
    _journal_change(
        client,
        "transmission",
        "2026-01-03T00:00:00",
        {"transmission.efficiency": 0.96},
        source="Паспорт передачи",
    )
    view = client.get(BASE + "/equipment", params={"at": "2026-01-04T00:00:00"}).json()
    origins = view["provenance"]["field_sources"]
    assert origins["motor.eta_nom"]["source"] == "Паспорт электродвигателя"
    assert origins["transmission.efficiency"]["source"] == "Паспорт передачи"


def test_unknown_transmission_efficiency_is_saved_as_unknown_not_unity(workflow):
    client, _ = workflow
    _journal_change(
        client,
        "transmission",
        "2026-01-02T00:00:00",
        {"transmission.efficiency": None},
        source="Проверка комплектности паспорта",
    )
    saved = client.get(BASE + "/equipment", params={"at": CONTEXT["timestamp"]}).json()
    assert saved["equipment"]["transmission"]["efficiency"] is None
    detail = client.post(BASE + "/loss-detail", json={**CONTEXT, "key": "hall"})
    assert detail.status_code == 200, detail.text
    detail = detail.json()
    assert detail["total_kw"] == pytest.approx(100)
    assert detail["status"] == "partial"
    assert detail["unallocated_kw"] == pytest.approx(67.14)
    unknown = {c["key"] for c in detail["components"] if c["power_kw"] is None}
    assert unknown == {"transmission_loss", "pump_loss"}


def _journal_change(client, component, at, changes, **extra):
    current = client.get(BASE + "/equipment-journal")
    assert current.status_code == 200, current.text
    response = client.post(
        BASE + "/equipment-journal",
        json={
            "component": component,
            "effective_at": at,
            "expected_revision": current.json()["revision"],
            "changes": changes,
            "reason": "repair",
            "evidence": "documented",
            "source": "Акт ремонта",
            "author": "Специалист",
            **extra,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_backdated_pump_repair_does_not_revert_later_motor_or_pump_changes(workflow):
    client, _ = workflow
    _journal_change(client, "motor", "2026-01-05T00:00:00", {"motor.eta_nom": 0.94})
    _journal_change(client, "pump", "2026-01-10T00:00:00", {"pump.eta_nom": 0.85})
    _journal_change(client, "pump", "2026-01-02T00:00:00", {"pump.eta_nom": 0.82})
    for at, pump_eta, motor_eta in [
        ("2026-01-01T12:00:00", 0.8, 0.9),
        ("2026-01-04T12:00:00", 0.82, 0.9),
        ("2026-01-06T12:00:00", 0.82, 0.94),
        ("2026-01-11T12:00:00", 0.85, 0.94),
    ]:
        equipment = client.get(BASE + "/equipment", params={"at": at}).json()["equipment"]
        assert equipment["pump"]["eta_nom"] == pump_eta
        assert equipment["motor"]["eta_nom"] == motor_eta
    audit = client.post(BASE + "/snapshot-audit", json=CONTEXT)
    assert audit.status_code == 200, audit.text
    assert audit.json()["audit"]["metrics"]["eta_nom"] == pytest.approx(0.82 * 0.9 * 0.98 * 0.97)


def test_journal_correction_changes_effective_date_without_erasing_original(workflow):
    client, _ = workflow
    saved = _journal_change(client, "pump", "2026-01-02T00:00:00", {"pump.eta_nom": 0.82})
    original = next(item for item in saved["items"] if item["changes"].get("pump.eta_nom") == 0.82)
    corrected = _journal_change(
        client,
        "pump",
        "2026-01-04T00:00:00",
        {"pump.eta_nom": 0.83},
        reason="correction",
        supersedes_id=original["id"],
        source="Исправленный акт",
    )
    archived = next(item for item in corrected["items"] if item["id"] == original["id"])
    assert archived["changes"]["pump.eta_nom"] == 0.82
    assert archived["superseded_by"] is not None
    before = client.get(BASE + "/equipment", params={"at": "2026-01-03T12:00:00"}).json()
    after = client.get(BASE + "/equipment", params={"at": "2026-01-05T12:00:00"}).json()
    assert before["equipment"]["pump"]["eta_nom"] == 0.8
    assert after["equipment"]["pump"]["eta_nom"] == 0.83
    origin = after["provenance"]["field_sources"]["pump.eta_nom"]
    assert origin["source"] == "Исправленный акт"
    assert origin["effective_at"] == "2026-01-04T00:00:00"
    assert origin["recorded_at"] != origin["effective_at"]


def test_estimated_efficiency_is_not_confirmed_measured_or_nominal_evidence(workflow):
    client, _ = workflow
    _journal_change(
        client,
        "pump",
        "2026-01-02T00:00:00",
        {"pump.eta_nom": 0.82},
        evidence="estimate",
        source="Оценка специалиста после осмотра",
    )
    readiness = client.post(BASE + "/data-requirements", json=CONTEXT)
    assert readiness.status_code == 200, readiness.text
    requirement = next(r for r in readiness.json()["requirements"] if r["key"] == "pump.eta_nom")
    assert requirement["status"] == "assumed"
    view = client.get(BASE + "/equipment", params={"at": CONTEXT["timestamp"]}).json()
    assert "pump.eta_nom" not in view["provenance"]["confirmed_fields"]


def test_monitoring_history_uses_each_components_effective_characteristics(workflow):
    client, db = workflow
    for metric, value, unit in [
        ("p_in", 1, "МПа"),
        ("p_out", 10, "МПа"),
        ("flow_rate", 36, "м³/ч"),
        ("power", 180, "кВт"),
        ("density", 1000, "кг/м³"),
    ]:
        db.add_measurement("workflow", "A", datetime(2026, 1, 6, 12), metric, value, unit)
    db.add_measurement("workflow", None, datetime(2026, 1, 6, 12), "p_bg", 9, "МПа")
    original = db.measurements("workflow", "A")
    _journal_change(client, "motor", "2026-01-05T00:00:00", {"motor.eta_nom": 0.94})
    _journal_change(client, "pump", "2026-01-02T00:00:00", {"pump.eta_nom": 0.82})
    history = client.get(
        "/objects/workflow/timeline",
        params={
            "aggregate_id": "A",
            "start": "2026-01-02",
            "end": "2026-01-06",
        },
    )
    assert history.status_code == 200, history.text
    points = {p["timestamp"]: p for p in history.json()["points"]}
    assert points["2026-01-02T12:00:00"]["nominal_efficiency"] == pytest.approx(
        0.82 * 0.9 * 0.98 * 0.97
    )
    assert points["2026-01-06T12:00:00"]["nominal_efficiency"] == pytest.approx(
        0.82 * 0.94 * 0.98 * 0.97
    )
    assert db.measurements("workflow", "A") == original


def test_snapshot_and_loss_provenance_use_repair_time_not_day_start(workflow):
    client, _ = workflow
    _journal_change(
        client, "motor", "2026-01-02T09:00:00", {"motor.eta_nom": 0.94}, source="Ремонт утром"
    )
    snapshot = client.post(BASE + "/snapshot-audit", json=CONTEXT)
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["audit"]["metrics"]["eta_nom"] == pytest.approx(0.8 * 0.94 * 0.98 * 0.97)
    detail = client.post(BASE + "/loss-detail", json={**CONTEXT, "key": "nominal_loss"})
    assert detail.status_code == 200, detail.text
    motor = next(
        item for item in detail.json()["components"][0]["inputs"] if item["key"] == "motor_eta_nom"
    )
    assert motor["value"] == 0.94
    assert "Ремонт утром" in motor["source"]


def test_later_legacy_passport_does_not_reintroduce_unchanged_old_pump_efficiency(workflow):
    client, db = workflow
    db.add_passport(
        "workflow",
        "A",
        valid_from=datetime(2026, 1, 5),
        pump_model="ЦНС36",
        pump_kind="центробежный",
        pump_q_nom=36,
        pump_h_nom=1000,
        pump_eta_nom=0.8,
        motor_model="ЭД",
        motor_p_nom=200,
        motor_eta_nom=0.94,
        transmission_eff=0.98,
        vfd=True,
    )
    _journal_change(client, "pump", "2026-01-02T00:00:00", {"pump.eta_nom": 0.82})
    for stamp in ["2026-01-03T12:00:00", "2026-01-06T12:00:00"]:
        equipment = client.get(BASE + "/equipment", params={"at": stamp}).json()["equipment"]
        assert equipment["pump"]["eta_nom"] == 0.82
    updated = client.get(BASE + "/equipment", params={"at": "2026-01-06T12:00:00"}).json()
    assert updated["equipment"]["motor"]["eta_nom"] == 0.94


def test_legacy_snapshot_losing_confirmation_does_not_revert_dated_journal_value(workflow):
    client, db = workflow
    with db._connection() as connection:
        aggregate_id = db._aggregate_id(connection, "workflow", "A", None)
        connection.execute(
            """UPDATE aggregate_passports SET source = ?, author = ?,
               confirmed_fields_json = ? WHERE aggregate_id = ?""",
            ("Первоначальный паспорт", "Инженер", '["pump.eta_nom"]', aggregate_id),
        )
    db.add_passport(
        "workflow",
        "A",
        valid_from=datetime(2026, 1, 5),
        pump_model="ЦНС36",
        pump_kind="центробежный",
        pump_q_nom=36,
        pump_h_nom=1000,
        pump_eta_nom=0.8,
        motor_model="ЭД",
        motor_p_nom=200,
        motor_eta_nom=0.94,
        transmission_eff=0.98,
        vfd=True,
    )
    _journal_change(client, "pump", "2026-01-02T00:00:00", {"pump.eta_nom": 0.82})
    view = client.get(BASE + "/equipment", params={"at": "2026-01-06T12:00:00"}).json()
    assert view["equipment"]["pump"]["eta_nom"] == 0.82
    assert view["provenance"]["field_sources"]["pump.eta_nom"]["source"] == "Акт ремонта"
