"""Consumer boundaries: scoped detail, provenance, history and no telemetry overwrite."""

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
