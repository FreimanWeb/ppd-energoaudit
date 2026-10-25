from datetime import UTC, datetime, timedelta

import pytest

from ppd_audit.db import AuditDatabase
from ppd_audit.services.demo import DEMO_OBJECT_ID, demo_network, seed_demo
from ppd_audit.services.telemetry_audit import run_snapshot_audit, telemetry_snapshots


def test_demo_well_history_is_complete_isolated_and_idempotent(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    now = datetime(2026, 10, 25, 20)
    seed_demo(db, now)
    assert {well["code"] for well in db.wells(DEMO_OBJECT_ID)} == {
        well["id"] for well in demo_network()["wells"]
    }
    histories = {}
    for well in db.wells(DEMO_OBJECT_ID):
        rows = db.well_history(DEMO_OBJECT_ID, well["code"])
        histories[well["code"]] = rows
        monthly = [row for row in rows if row["record_kind"] == "monthly_actual"]
        assert len({row["observed_at"] for row in monthly}) == 12
        assert {row["metric"] for row in monthly} >= {"p_well", "p_bg", "injection_volume_m3"}
        assert {row["record_kind"] for row in rows} == {"monthly_actual", "current", "study"}
        assert all(row["source_file"].startswith("synthetic://") for row in rows)
        assert all(row["value"] > 0 for row in rows)
    seed_demo(db, now)
    assert histories == {code: db.well_history(DEMO_OBJECT_ID, code) for code in histories}
    assert db.wells("kns54an") == []


def test_demo_is_append_only_and_isolated(tmp_path):
    db = AuditDatabase(tmp_path / 'audit.sqlite')
    db.migrate()
    db.upsert_plant('real', 'Реальная КНС', 'НГДУ', 'пресная', 'кнс')
    db.add_measurement('real', None, datetime(2026, 10, 18), 'p_bg', 8, 'МПа')
    real = db.measurements('real')
    now = datetime(2026, 10, 18, 9, tzinfo=UTC)
    assert seed_demo(db, now) > 6000
    rows = db.measurements(DEMO_OBJECT_ID)
    stamps = sorted({datetime.fromisoformat(row['timestamp']) for row in rows})
    assert stamps[-1] == datetime(2026, 10, 18, 12)
    assert stamps[-1] - stamps[0] == timedelta(days=90)
    assert all(b - a == timedelta(hours=2) for a, b in zip(stamps, stamps[1:], strict=False))
    assert all(row['source_kind'] == 'demo' for row in rows)
    assert all(row['source_file'].startswith('synthetic://') for row in rows)
    assert db.plants(include_examples=True)[0]['code'] == DEMO_OBJECT_ID
    assert DEMO_OBJECT_ID not in {plant['code'] for plant in db.plants()}
    assert seed_demo(db, now) == 0
    assert db.measurements(DEMO_OBJECT_ID) == rows
    assert seed_demo(db, now + timedelta(hours=2)) == 13
    assert db.measurements(DEMO_OBJECT_ID)[:len(rows)] == rows
    assert db.measurements('real') == real


def test_demo_pressure_and_energy_are_feasible(tmp_path):
    db = AuditDatabase(tmp_path / 'audit.sqlite')
    db.migrate()
    seed_demo(db, datetime(2026, 10, 18, 12))
    rows = db.measurements(DEMO_OBJECT_ID)
    grouped = {}
    for row in rows:
        if row['metric'] == 'p_bg':
            grouped[row['timestamp']] = row['value']
    for code in ("НА-1", "НА-2"):
        values_by_time = {}
        for row in db.measurements(DEMO_OBJECT_ID, code):
            values_by_time.setdefault(row['timestamp'], {})[row['metric']] = row['value']
        sec = []
        for stamp, values in values_by_time.items():
            assert 0 < values['p_in'] < grouped[stamp] < values['p_out']
            hydraulic = (values['p_out'] - values['p_in']) * values['flow_rate'] / 3.6
            assert 0 < hydraulic < values['power'] * .97 * .96
            assert values['density'] == 1000
            sec.append(values['power'] / values['flow_rate'])
        if code == "НА-1":
            assert sec[-1] > sec[-12 * 10] * 1.1
        else:
            assert sec[-1] < sec[-12 * 10] * 1.05
    network = demo_network()
    assert network['object_id'] == DEMO_OBJECT_ID
    assert len(network['wells']) == 6
    assert all(segment['length_m'] > 0 for segment in network['segments'])
    assert sum(segment['length_m'] for segment in network['segments']) == pytest.approx(7000)


def test_demo_has_ready_snapshot_audit(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    seed_demo(db, datetime(2026, 10, 18, 12))
    start, end = datetime(2026, 10, 17), datetime(2026, 10, 18)
    snapshots = telemetry_snapshots(db, DEMO_OBJECT_ID, "НА-1", start, end)
    assert len(snapshots) == 48
    audit = run_snapshot_audit(
        db, DEMO_OBJECT_ID, "НА-1", start, end, snapshots[-1].timestamp,
        track_clarifications=False,
    )
    assert audit.quality.status == "ready"
    assert audit.audit.decomposition.p_bg_useful > 0


def test_demo_adds_second_pump_to_existing_seed_without_changing_first(tmp_path):
    from ppd_audit.services.monitoring import object_timeline

    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    now = datetime(2026, 10, 18, 12)
    seed_demo(db, now)
    # Reproduce a database seeded by the original single-pump demo.
    with db._connection() as connection:
        connection.execute(
            "DELETE FROM telemetry_measurements WHERE aggregate_id IN "
            "(SELECT id FROM aggregates WHERE code = 'НА-2')"
        )
        connection.execute(
            "DELETE FROM aggregate_passports WHERE aggregate_id IN "
            "(SELECT id FROM aggregates WHERE code = 'НА-2')"
        )
        connection.execute("DELETE FROM aggregates WHERE code = 'НА-2'")
    first = db.measurements(DEMO_OBJECT_ID, "НА-1")
    assert seed_demo(db, now) == len(first)
    assert db.measurements(DEMO_OBJECT_ID, "НА-1") == first
    second = db.measurements(DEMO_OBJECT_ID, "НА-2")
    assert len(second) == len(first)
    assert db.aggregate(DEMO_OBJECT_ID, "НА-2")["role"] == "работа"
    assert second[-1]["source_kind"] == "demo"
    assert seed_demo(db, now) == 0

    timelines = [
        object_timeline(db, DEMO_OBJECT_ID, aggregate_id=code)
        for code in (None, "НА-1", "НА-2")
    ]
    latest = [
        next(point for point in reversed(result["points"]) if point["power_kw"] is not None)
        for result in timelines
    ]
    station, one, two = latest
    assert one["flow_m3h"] != two["flow_m3h"]
    assert station["power_kw"] == pytest.approx(one["power_kw"] + two["power_kw"])
    assert station["flow_m3h"] == pytest.approx(one["flow_m3h"] + two["flow_m3h"])
    assert station["sec_kwh_m3"] == pytest.approx(
        station["power_kw"] / station["flow_m3h"]
    )
    start, end = datetime(2026, 10, 17), datetime(2026, 10, 18)
    snapshots = telemetry_snapshots(db, DEMO_OBJECT_ID, "НА-2", start, end)
    audit = run_snapshot_audit(
        db, DEMO_OBJECT_ID, "НА-2", start, end, snapshots[-1].timestamp,
        track_clarifications=False,
    )
    assert audit.quality.status == "ready"
    assert 0 < audit.audit.decomposition.p_bg_useful
