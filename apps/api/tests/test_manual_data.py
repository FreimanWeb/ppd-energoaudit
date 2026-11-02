"""Equipment journal boundaries, replacement semantics, and safe legacy migration."""

from datetime import datetime
from importlib import import_module

import pytest
from fastapi.testclient import TestClient

from ppd_audit.db import AuditDatabase


BASE = "/objects/manual/aggregates/A"


@pytest.fixture
def store(tmp_path, monkeypatch):
    db = AuditDatabase(tmp_path / "manual.sqlite")
    db.migrate()
    db.upsert_plant("manual", "Объект", "НГДУ", "пресная", "кнс")
    for code in ("A", "B"):
        db.upsert_aggregate("manual", code, "работа")
    db.add_passport(
        "manual",
        "A",
        valid_from=datetime(2026, 1, 1),
        pump_model="Насос",
        pump_kind="центробежный",
        pump_h_nom=1000,
        pump_q_nom=100,
        pump_eta_nom=0.8,
        motor_model="ЭД",
        motor_p_nom=200,
        motor_eta_nom=0.9,
        transmission_eff=0.98,
    )
    main = import_module("ppd_audit.api.main")
    monkeypatch.setattr(main, "_database", lambda: db)
    return TestClient(main.app), db


def publish(client, changes, *, component="pump", at="2026-01-02T00:00:00", base=BASE, **extra):
    head = client.get(base + "/equipment-journal").json()["revision"]
    return client.post(
        base + "/equipment-journal",
        json={
            "component": component,
            "effective_at": at,
            "expected_revision": head,
            "changes": changes,
            "reason": "repair",
            "evidence": "documented",
            "source": "Акт",
            "author": "Инженер",
            **extra,
        },
    )


def test_replacement_does_not_inherit_old_pump_characteristics_or_touch_motor(store):
    client, _ = store
    saved = publish(
        client, {"pump.model": "Новый насос", "pump.kind": "центробежный"}, reason="replacement"
    )
    assert saved.status_code == 200, saved.text
    entry = saved.json()["items"][0]
    assert entry["resets"]["pump.eta_nom"] is None
    assert "pump.eta_nom" not in entry["changes"]
    view = client.get(BASE + "/equipment", params={"at": "2026-01-03"}).json()
    assert view["equipment"]["pump"]["eta_nom"] is None
    assert view["equipment"]["pump"]["q_nom"] is None
    assert view["equipment"]["motor"]["eta_nom"] == 0.9
    assert "pump.eta_nom" not in view["provenance"]["confirmed_fields"]
    original_id = entry["id"]
    correction = publish(
        client,
        {"pump.model": "Исправленная модель", "pump.kind": "центробежный"},
        reason="correction",
        supersedes_id=original_id,
    )
    assert correction.status_code == 200, correction.text
    after = client.get(BASE + "/equipment", params={"at": "2026-01-03"}).json()
    assert after["equipment"]["pump"]["model"] == "Исправленная модель"
    assert after["equipment"]["pump"]["eta_nom"] is None
    assert "pump.eta_nom" not in after["provenance"]["confirmed_fields"]


def test_same_time_field_collision_requires_explicit_correction_but_other_fields_are_independent(
    store,
):
    client, _ = store
    assert publish(client, {"pump.eta_nom": 0.82}).status_code == 200
    assert publish(client, {"motor.eta_nom": 0.94}, component="motor").status_code == 200
    collision = publish(client, {"pump.eta_nom": 0.83})
    assert collision.status_code == 409, collision.text
    view = client.get(BASE + "/equipment", params={"at": "2026-01-03"}).json()["equipment"]
    assert view["pump"]["eta_nom"] == 0.82
    assert view["motor"]["eta_nom"] == 0.94


def test_correction_cannot_drop_original_fields_or_change_another_aggregates_record(store):
    client, _ = store
    saved = publish(client, {"pump.eta_nom": 0.82, "pump.q_nom": 110}).json()
    entry = saved["items"][0]
    dropped = publish(
        client, {"pump.eta_nom": 0.83}, reason="correction", supersedes_id=entry["id"]
    )
    assert dropped.status_code == 409
    foreign = publish(
        client,
        entry["changes"],
        base="/objects/manual/aggregates/B",
        reason="correction",
        supersedes_id=entry["id"],
    )
    assert foreign.status_code == 404
    assert (
        client.get(BASE + "/equipment", params={"at": "2026-01-03"}).json()["equipment"]["pump"][
            "q_nom"
        ]
        == 110
    )


@pytest.mark.parametrize(
    "component,changes",
    [
        ("pump", {"motor.eta_nom": 0.9}),
        ("pump", {"pump.unknown": 1}),
        ("pump", {"pump.eta_nom": 90}),
        ("pump", {"pump.eta_nom": "NaN"}),
        ("pump", {"pump.eta_nom": True}),
        ("motor", {"motor.p_nom": -1}),
        ("vfd", {"vfd": "yes"}),
        ("pump", {}),
        ("pump", {"pump.curve_qeta": [[10, 0.5], [10, 0.6]]}),
    ],
)
def test_invalid_journal_values_are_rejected_without_publishing(store, component, changes):
    client, _ = store
    result = publish(client, changes, component=component)
    assert result.status_code == 422, result.text
    assert client.get(BASE + "/equipment-journal").json()["items"] == []


def test_estimated_curve_cannot_claim_verified_installed_binding(store):
    client, _ = store
    response = publish(
        client,
        {
            "pump.curve_source": {
                "kind": "experimental",
                "reference": "Оценка",
                "model": "Насос",
                "speed_rpm": 3000,
                "verified": True,
            },
            "pump.curve_qeta": [[10, 0.5], [20, 0.7], [30, 0.6]],
        },
        evidence="estimate",
    )
    assert response.status_code == 200, response.text
    equipment = client.get(BASE + "/equipment", params={"at": "2026-01-03"}).json()
    assert equipment["equipment"]["pump"]["curve_source"]["verified"] is False
    assert "pump.curve_qeta" not in equipment["provenance"]["confirmed_fields"]


def test_new_journal_can_fill_equipment_without_a_legacy_passport(store):
    client, _ = store
    base = "/objects/manual/aggregates/B"
    response = publish(client, {"pump.model": "Насос Б", "pump.eta_nom": 0.75}, base=base)
    assert response.status_code == 200, response.text
    equipment = client.get(base + "/equipment", params={"at": "2026-01-03"}).json()["equipment"]
    assert equipment["pump"]["eta_nom"] == 0.75
    assert equipment["motor"]["eta_nom"] is None
    assert equipment["transmission"]["efficiency"] is None


def test_unrelated_invalid_legacy_value_does_not_prevent_component_repair(store):
    client, db = store
    with db._connection() as connection:
        connection.execute("UPDATE aggregate_passports SET pump_eta_nom = 1.5")
    response = publish(client, {"motor.eta_nom": 0.94}, component="motor")
    assert response.status_code == 200, response.text
    equipment = client.get(BASE + "/equipment", params={"at": "2026-01-03"}).json()["equipment"]
    assert equipment["motor"]["eta_nom"] == 0.94
    assert equipment["pump"]["eta_nom"] == 1.5


def test_migration_preserves_passports_and_archived_measurements(store):
    _, db = store
    with db._connection() as connection:
        aggregate_id = db._aggregate_id(connection, "manual", "A", None)
        connection.execute(
            "INSERT INTO manual_measurements VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
            (
                aggregate_id,
                "2026-01-02T12:00:00",
                '{"rho":1000,"p_in":1,"p_out":10,"q_fact":100,"p_electric":300}',
                "Архив",
                "Комментарий",
                "Автор",
                "2026-01-09T12:00:00+00:00",
            ),
        )
        before = [
            tuple(row)
            for row in connection.execute("SELECT * FROM aggregate_passports ORDER BY id")
        ]
        archived = [tuple(row) for row in connection.execute("SELECT * FROM manual_measurements")]
        connection.execute("DROP TABLE equipment_journal")
        connection.execute("PRAGMA user_version = 20")
    db.migrate()
    db.migrate()
    with db._connection() as connection:
        assert [
            tuple(row)
            for row in connection.execute("SELECT * FROM aggregate_passports ORDER BY id")
        ] == before
        assert [
            tuple(row) for row in connection.execute("SELECT * FROM manual_measurements")
        ] == archived
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()


def test_unprovided_motor_type_after_replacement_is_unknown_not_confirmed_asynchronous(store):
    client, _ = store
    response = publish(
        client,
        {"motor.model": "Новый ЭД", "motor.p_nom": 220, "motor.eta_nom": 0.92},
        component="motor",
        reason="replacement",
    )
    assert response.status_code == 200, response.text
    requirements = client.get(BASE + "/data-requirements", params={"at": "2026-01-03"}).json()[
        "requirements"
    ]
    motor_type = next(row for row in requirements if row["key"] == "motor.synchronous")
    assert motor_type["status"] == "missing"
    assert motor_type["value"] is None
