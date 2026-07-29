from datetime import date, datetime, timedelta

import pytest

from ppd_audit.db import AuditDatabase
from ppd_audit.services.telemetry_audit import (
    build_regime,
    object_from_database,
    run_snapshot_audit,
    run_telemetry_audit,
    telemetry_date_statuses,
    telemetry_day_status,
    telemetry_snapshots,
)


def _database_with_aggregate(tmp_path) -> AuditDatabase:
    database = AuditDatabase(tmp_path / "audit.sqlite")
    database.migrate()
    database.upsert_plant("kns97", "КНС-97", "Елховнефть", "пресная", "кнс")
    database.upsert_aggregate("kns97", "НА-02", "работа")
    database.add_passport(
        "kns97",
        "НА-02",
        valid_from=datetime(2020, 1, 1),
        pump_model="ЦНС 40-1000(-2)",
        pump_kind="центробежный",
        pump_q_nom=40.0,
        pump_h_nom=1000.0,
        pump_eta_nom=0.52,
        motor_model="ВАО2-450LB-2У2",
        motor_p_nom=400.0,
        motor_eta_nom=0.949,
        transmission_model="СТ-А Ц-1-280-4,55-12-1",
        transmission_ratio=4.55,
    )
    return database


def test_build_regime_reduces_telemetry_window(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for index, (p_in, p_out, power) in enumerate(
        [(1.0, 10.2, 200.0), (1.2, 10.4, 210.0), (1.4, 10.6, 220.0)]
    ):
        timestamp = start + timedelta(minutes=index)
        database.add_measurement("kns97", "НА-02", timestamp, "p_in", p_in, "МПа")
        database.add_measurement("kns97", "НА-02", timestamp, "p_out", p_out, "МПа")
        database.add_measurement("kns97", "НА-02", timestamp, "power", power, "кВт")
    for metric, value, unit in [
        ("q_day", 2400.0, "м³/сут"),
        ("runtime", 24.0, "ч"),
        ("energy", 4800.0, "кВт·ч"),
        ("density", 1000.0, "кг/м³"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)

    regime = build_regime(database, "kns97", "НА-02", start, start + timedelta(days=1))

    assert regime.p_in == pytest.approx(1.2)
    assert regime.p_out == pytest.approx(10.4)
    assert regime.p_electric == pytest.approx(200.0)
    assert regime.q_day == pytest.approx(2400.0)
    assert regime.t == pytest.approx(24.0)
    assert regime.w == pytest.approx(4800.0)


def test_build_regime_uses_pressure_pair_near_positive_power(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit, timestamp in [
        ("p_in", 1.2, "МПа", start),
        ("p_out", 10.4, "МПа", start),
        ("power", 210.0, "кВт", start),
        ("density", 1000.0, "кг/м³", start),
        ("p_in", 3.0, "МПа", start + timedelta(hours=8)),
        ("p_out", 3.0, "МПа", start + timedelta(hours=8)),
        ("power", 0.0, "кВт", start + timedelta(hours=8)),
    ]:
        database.add_measurement("kns97", "НА-02", timestamp, metric, value, unit)

    regime = build_regime(database, "kns97", "НА-02", start, start + timedelta(days=1))

    assert regime.p_in == pytest.approx(1.2)
    assert regime.p_out == pytest.approx(10.4)


def test_build_regime_averages_daily_operating_pressure_and_power(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for index, (p_in, p_out, power) in enumerate(
        [(1.0, 10.0, 200.0), (2.0, 20.0, 400.0), (10.0, 50.0, 400.0)]
    ):
        timestamp = start + timedelta(minutes=30 * index)
        database.add_measurement("kns97", "НА-02", timestamp, "p_in", p_in, "МПа")
        database.add_measurement("kns97", "НА-02", timestamp, "p_out", p_out, "МПа")
        database.add_measurement("kns97", "НА-02", timestamp, "power", power, "кВт")
    for metric, value, unit in [
        ("density", 1000.0, "кг/м³"),
        ("q_day", 600.0, "м³/сут"),
        ("runtime", 2.0, "ч"),
        ("energy", 600.0, "кВт·ч"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)

    regime = build_regime(database, "kns97", "НА-02", start, start + timedelta(days=1))

    assert regime.p_in == pytest.approx((1 + 2 + 10 * 46) / 48)
    assert regime.p_out == pytest.approx((10 + 20 + 50 * 46) / 48)
    assert regime.p_electric == pytest.approx(300.0)


def test_build_regime_uses_held_power_when_energy_is_absent(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.0, "МПа"),
        ("p_out", 10.0, "МПа"),
        ("density", 1000.0, "кг/м³"),
        ("q_day", 600.0, "м³/сут"),
        ("runtime", 2.0, "ч"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)
    database.add_measurement("kns97", "НА-02", start, "power", 200.0, "кВт")
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(hours=1), "power", 400.0, "кВт"
    )

    regime = build_regime(
        database, "kns97", "НА-02", start, start + timedelta(hours=1, minutes=1)
    )

    assert regime.p_electric == pytest.approx(200.0)


def test_build_regime_carries_power_until_pressure_appears(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    database.add_measurement("kns97", "НА-02", start, "power", 210.0, "кВт")
    database.add_measurement("kns97", "НА-02", start, "density", 1000.0, "кг/м³")
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(minutes=31), "p_in", 1.2, "МПа"
    )
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(minutes=31), "p_out", 10.4, "МПа"
    )

    regime = build_regime(database, "kns97", "НА-02", start, start + timedelta(days=1))

    assert regime.p_in == pytest.approx(1.2)
    assert regime.p_out == pytest.approx(10.4)


def test_build_regime_carries_pressure_over_operating_power_points(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 210.0, "кВт"),
        ("density", 1000.0, "кг/м³"),
        ("q_day", 48.0, "м³/сут"),
        ("runtime", 2.0, "ч"),
        ("energy", 420.0, "кВт·ч"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(minutes=60), "power", 210.0, "кВт"
    )

    regime = build_regime(database, "kns97", "НА-02", start, start + timedelta(days=1))

    assert regime.p_in == pytest.approx(1.2)
    assert regime.p_out == pytest.approx(10.4)


def test_build_regime_uses_snapshot_when_daily_coverage_is_incomplete(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 210.0, "кВт"),
        ("density", 1000.0, "кг/м³"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(minutes=60), "power", 210.0, "кВт"
    )

    regime = build_regime(
        database,
        "kns97",
        "НА-02",
        start,
        start + timedelta(days=1),
        require_daily_pressure_coverage=False,
    )

    assert regime.p_in == pytest.approx(1.2)
    assert regime.p_out == pytest.approx(10.4)


def test_snapshot_ignores_pressure_pair_with_negative_head(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for timestamp, p_in, p_out in [
        (start, 1.2, 10.4),
        (start + timedelta(minutes=10), 2.1, 2.0),
    ]:
        database.add_measurement("kns97", "НА-02", timestamp, "p_in", p_in, "МПа")
        database.add_measurement("kns97", "НА-02", timestamp, "p_out", p_out, "МПа")
        database.add_measurement("kns97", "НА-02", timestamp, "power", 210.0, "кВт")
    database.add_measurement("kns97", "НА-02", start, "density", 1000.0, "кг/м³")

    regime = build_regime(
        database,
        "kns97",
        "НА-02",
        start,
        start + timedelta(days=1),
        require_daily_pressure_coverage=False,
    )

    assert regime.p_in == pytest.approx(1.2)
    assert regime.p_out == pytest.approx(10.4)


def test_snapshot_uses_held_power_after_pressure_appears(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    database.add_measurement("kns97", "НА-02", start, "power", 210.0, "кВт")
    database.add_measurement("kns97", "НА-02", start, "density", 1000.0, "кг/м³")
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(minutes=6), "p_in", 1.2, "МПа"
    )
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(minutes=6), "p_out", 10.4, "МПа"
    )

    regime = build_regime(
        database,
        "kns97",
        "НА-02",
        start,
        start + timedelta(days=1),
        require_daily_pressure_coverage=False,
    )

    assert regime.p_in == pytest.approx(1.2)
    assert regime.p_out == pytest.approx(10.4)


def test_snapshot_uses_power_slot_after_fast_pressure_transition(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for timestamp, p_in, p_out in [
        (start, 1.2, 10.4),
        (start + timedelta(seconds=10), 1.5, 10.7),
    ]:
        database.add_measurement("kns97", "НА-02", timestamp, "p_in", p_in, "МПа")
        database.add_measurement("kns97", "НА-02", timestamp, "p_out", p_out, "МПа")
    database.add_measurement("kns97", "НА-02", start, "power", 210.0, "кВт")
    database.add_measurement("kns97", "НА-02", start, "density", 1000.0, "кг/м³")

    regime = build_regime(
        database,
        "kns97",
        "НА-02",
        start,
        start + timedelta(days=1),
        require_daily_pressure_coverage=False,
    )

    assert regime.p_in == pytest.approx(1.5)
    assert regime.p_out == pytest.approx(10.7)


def test_telemetry_snapshots_use_power_timestamp_and_pressure_age(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    database.add_measurement("kns97", "НА-02", start, "p_in", 1.2, "МПа")
    database.add_measurement("kns97", "НА-02", start, "p_out", 10.4, "МПа")
    database.add_measurement("kns97", "НА-02", start + timedelta(minutes=4), "power", 210.0, "кВт")
    database.add_measurement("kns97", None, start + timedelta(minutes=2), "p_bg", 9.8, "МПа")

    snapshots = telemetry_snapshots(
        database, "kns97", "НА-02", start, start + timedelta(days=1)
    )

    assert len(snapshots) == 1
    assert snapshots[0].timestamp == start + timedelta(minutes=4)
    assert snapshots[0].power_kw == pytest.approx(210.0)
    assert snapshots[0].p_bg_mpa == pytest.approx(9.8)
    assert snapshots[0].p_bg_age == timedelta(minutes=2)


def test_telemetry_snapshots_hold_pressure_values_until_the_next_change(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    previous_second = start - timedelta(seconds=1)
    database.add_measurement("kns97", "НА-02", previous_second, "p_in", 1.2, "МПа")
    database.add_measurement("kns97", "НА-02", previous_second, "p_out", 10.4, "МПа")
    database.add_measurement("kns97", None, previous_second, "p_bg", 9.8, "МПа")
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(seconds=10), "power", 210.0, "кВт"
    )

    snapshots = telemetry_snapshots(
        database, "kns97", "НА-02", start, start + timedelta(days=1)
    )

    assert len(snapshots) == 1
    assert snapshots[0].timestamp == start + timedelta(seconds=10)
    assert snapshots[0].p_in_mpa == pytest.approx(1.2)
    assert snapshots[0].p_out_mpa == pytest.approx(10.4)
    assert snapshots[0].p_bg_mpa == pytest.approx(9.8)
    assert snapshots[0].p_bg_age == timedelta(seconds=11)


def test_telemetry_snapshots_hold_power_for_missing_half_hour_slot(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)
    database.add_measurement("kns97", "НА-02", start, "power", 210.0, "кВт")
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(hours=1), "power", 220.0, "кВт"
    )

    snapshots = telemetry_snapshots(
        database, "kns97", "НА-02", start, start + timedelta(hours=1, minutes=1)
    )

    assert [(snapshot.timestamp, snapshot.power_kw) for snapshot in snapshots] == [
        (start, 210.0),
        (start + timedelta(minutes=30), 210.0),
        (start + timedelta(hours=1), 220.0),
    ]


def test_telemetry_snapshots_hold_single_aligned_power_value(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 210.0, "кВт"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)

    snapshots = telemetry_snapshots(
        database, "kns97", "НА-02", start, start + timedelta(hours=1, minutes=1)
    )

    assert [(snapshot.timestamp, snapshot.power_kw) for snapshot in snapshots] == [
        (start, 210.0),
        (start + timedelta(minutes=30), 210.0),
        (start + timedelta(hours=1), 210.0),
    ]


def test_telemetry_snapshots_exclude_pair_when_discharge_is_not_above_manifold(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    database.add_measurement("kns97", "НА-02", start, "p_in", 1.2, "МПа")
    database.add_measurement("kns97", "НА-02", start, "p_out", 8.0, "МПа")
    database.add_measurement("kns97", "НА-02", start, "power", 210.0, "кВт")
    database.add_measurement("kns97", None, start, "p_bg", 8.0, "МПа")

    snapshots = telemetry_snapshots(
        database, "kns97", "НА-02", start, start + timedelta(days=1)
    )

    assert snapshots == []


def test_telemetry_snapshots_exclude_only_power_slot_near_fast_pressure_change(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    database.add_measurement("kns97", "НА-02", start, "p_in", 1.2, "МПа")
    database.add_measurement("kns97", "НА-02", start, "p_out", 10.4, "МПа")
    database.add_measurement("kns97", "НА-02", start, "power", 210.0, "кВт")
    database.add_measurement("kns97", None, start, "p_bg", 9.8, "МПа")
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(seconds=10), "p_out", 10.7, "МПа"
    )

    snapshots = telemetry_snapshots(
        database, "kns97", "НА-02", start, start + timedelta(days=1)
    )

    assert snapshots[0].timestamp == start + timedelta(minutes=30)
    assert snapshots[0].p_out_mpa == pytest.approx(10.7)


def test_telemetry_snapshots_hold_pressure_pair_until_positive_power(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    database.add_measurement("kns97", "НА-02", start, "p_in", 1.2, "МПа")
    database.add_measurement("kns97", "НА-02", start, "p_out", 10.4, "МПа")
    database.add_measurement("kns97", None, start, "p_bg", 9.8, "МПа")
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(minutes=6), "power", 210.0, "кВт"
    )

    snapshots = telemetry_snapshots(
        database, "kns97", "НА-02", start, start + timedelta(days=1)
    )

    assert len(snapshots) == 1
    assert snapshots[0].timestamp == start + timedelta(minutes=6)


def test_snapshot_audit_marks_daily_totals_as_assumptions(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("density", 1000.0, "кг/м³"),
        ("q_day", 48.0, "м³/сут"),
        ("runtime", 2.0, "ч"),
        ("energy", 420.0, "кВт·ч"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)
    database.add_measurement(
        "kns97",
        "НА-02",
        start,
        "p_in",
        1.2,
        "МПа",
        source_kind="excel",
        source_file="КНС-97.xlsx",
        source_sheet="Измерения",
        source_row=42,
        source_tag="НА-02",
        source_label="Давление на приёме",
    )
    database.add_measurement("kns97", "НА-02", start + timedelta(minutes=4), "power", 210.0, "кВт")

    snapshot = run_snapshot_audit(
        database,
        "kns97",
        "НА-02",
        start,
        start + timedelta(days=1),
        start + timedelta(minutes=4),
    )

    assert snapshot.audit.regime.p_in == pytest.approx(1.2)
    assert snapshot.audit.regime.p_out == pytest.approx(10.4)
    assert snapshot.uses_daily_flow is True
    assert snapshot.uses_daily_power is True
    assert snapshot.annual_runtime_is_assumed is True
    assert snapshot.quality.status == "assumptions"
    assert snapshot.quality.basis["flow"] == "Q_сут / T_сут"
    assert snapshot.sources["p_вх"] == (
        "excel · КНС-97.xlsx · Измерения · 42 · НА-02 · Давление на приёме"
    )


def test_snapshot_audit_marks_conflicting_daily_totals_unfit(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.0, "МПа"),
        ("p_out", 4.0, "МПа"),
        ("power", 100.0, "кВт"),
        ("density", 1000.0, "кг/м³"),
        ("q_day", 100.0, "м³/сут"),
        ("runtime", 2.0, "ч"),
        ("energy", 100.0, "кВт·ч"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)

    snapshot = run_snapshot_audit(
        database, "kns97", "НА-02", start, start + timedelta(days=1), start
    )

    assert snapshot.quality.status == "unfit"
    assert {"energy_mismatch", "runtime_mismatch"} <= set(snapshot.quality.codes)


def test_snapshot_audit_does_not_reconcile_partial_power_series(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.0, "МПа"),
        ("p_out", 4.0, "МПа"),
        ("density", 1000.0, "кг/м³"),
        ("q_day", 50.0, "м³/сут"),
        ("runtime", 2.0, "ч"),
        ("energy", 100.0, "кВт·ч"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(minutes=30), "power", 100.0, "кВт"
    )

    snapshot = run_snapshot_audit(
        database,
        "kns97",
        "НА-02",
        start,
        start + timedelta(days=1),
        start + timedelta(minutes=30),
    )

    assert snapshot.quality.status == "assumptions"
    assert {"energy_mismatch", "runtime_mismatch"}.isdisjoint(snapshot.quality.codes)


def test_build_regime_preserves_zero_daily_flow(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.0, "МПа"),
        ("p_out", 4.0, "МПа"),
        ("power", 100.0, "кВт"),
        ("density", 1000.0, "кг/м³"),
        ("q_day", 0.0, "м³/сут"),
        ("runtime", 2.0, "ч"),
        ("energy", 100.0, "кВт·ч"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)

    regime = build_regime(database, "kns97", "НА-02", start, start + timedelta(days=1))

    assert regime.q_day == 0.0


def test_telemetry_day_status_rejects_unfit_snapshot(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.0, "МПа"),
        ("p_out", 4.0, "МПа"),
        ("power", 100.0, "кВт"),
        ("density", 1000.0, "кг/м³"),
        ("q_day", 100.0, "м³/сут"),
        ("runtime", 2.0, "ч"),
        ("energy", 100.0, "кВт·ч"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)

    assert telemetry_day_status(database, "kns97", "НА-02", start.date()) == "unfit"


def test_snapshot_audit_resolves_t_year_clarification_with_complete_runtime(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    end = start + timedelta(days=1)
    database.upsert_clarification(
        "kns97",
        "НА-02",
        field="t_year",
        provisional_value="8760",
        reason="Нет полного года моточасов",
    )
    for day in range(365):
        database.add_measurement(
            "kns97", "НА-02", end - timedelta(days=365 - day), "runtime", 20.0, "ч"
        )
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 210.0, "кВт"),
        ("density", 1000.0, "кг/м³"),
        ("q_day", 48.0, "м³/сут"),
        ("energy", 420.0, "кВт·ч"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)

    snapshot = run_snapshot_audit(database, "kns97", "НА-02", start, end, start)

    assert snapshot.annual_runtime_is_assumed is False
    assert database.clarifications("kns97", "НА-02") == []


def test_date_statuses_marks_snapshot_when_daily_coverage_is_incomplete(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 210.0, "кВт"),
        ("density", 1000.0, "кг/м³"),
        ("q_day", 48.0, "м³/сут"),
        ("runtime", 2.0, "ч"),
        ("energy", 420.0, "кВт·ч"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(minutes=60), "power", 210.0, "кВт"
    )
    database.add_measurement(
        "kns97", "НА-02", start + timedelta(hours=2), "power", 0.0, "кВт"
    )

    statuses = telemetry_date_statuses(database, "kns97", "НА-02", [start.date()])

    assert statuses == {start.date(): "ready"}


def test_telemetry_day_status_is_insufficient_when_snapshot_has_no_flow(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 210.0, "кВт"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)

    status = telemetry_day_status(database, "kns97", "НА-02", start.date())

    assert status == "insufficient"


def test_telemetry_audit_uses_passport_and_reduced_regime(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 210.0, "кВт"),
        ("q_day", 2400.0, "м³/сут"),
        ("runtime", 24.0, "ч"),
        ("density", 1000.0, "кг/м³"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)

    result = run_telemetry_audit(database, "kns97", "НА-02", start, start + timedelta(days=1))

    assert result.aggregate_id == "НА-02"
    assert result.regime.p_out == pytest.approx(10.4)
    assert result.sec_fact > 0


def test_telemetry_audit_uses_and_marks_annual_runtime_fallback(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 210.0, "кВт"),
        ("q_day", 2400.0, "м³/сут"),
        ("runtime", 24.0, "ч"),
        ("density", 1000.0, "кг/м³"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)

    result = run_telemetry_audit(database, "kns97", "НА-02", start, start + timedelta(days=1))

    assert result.spec.regime.t_year == 8760.0
    assert database.clarifications("kns97", "НА-02")[0]["field"] == "t_year"


def test_build_regime_rejects_station_flow_for_aggregate(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 210.0, "кВт"),
        ("q_day", 2400.0, "м³/сут"),
        ("runtime", 24.0, "ч"),
        ("density", 1000.0, "кг/м³"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)
    database.add_measurement("kns97", None, start, "q_day", 2400.0, "м³/сут")

    with pytest.raises(ValueError, match="станционный расход"):
        build_regime(database, "kns97", "НА-02", start, start + timedelta(days=1))


def test_build_regime_uses_persisted_density_when_series_has_none(tmp_path):
    database = AuditDatabase(tmp_path / "audit.sqlite")
    database.migrate()
    database.upsert_plant(
        "kns97",
        "КНС-97",
        "Елховнефть",
        "пресная",
        "кнс",
        default_density=1000.0,
    )
    database.upsert_aggregate("kns97", "НА-02", "работа")
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 210.0, "кВт"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)

    regime = build_regime(database, "kns97", "НА-02", start, start + timedelta(days=1))

    assert regime.rho == pytest.approx(1000.0)


def test_object_from_database_uses_persisted_passport(tmp_path):
    database = _database_with_aggregate(tmp_path)

    obj = object_from_database(database, "kns97", datetime(2026, 7, 24))

    assert obj.name == "КНС-97"
    assert obj.aggregate("НА-02").pump.model == "ЦНС 40-1000(-2)"
    assert obj.aggregate("НА-02").transmission.model == "СТ-А Ц-1-280-4,55-12-1"
    assert obj.aggregate("НА-02").transmission.ratio == pytest.approx(4.55)
    assert obj.aggregate("НА-02").regime is None


def test_object_from_database_can_load_selected_aggregate_when_others_have_no_passport(tmp_path):
    database = _database_with_aggregate(tmp_path)
    database.upsert_aggregate("kns97", "НА-1", "работа")

    obj = object_from_database(database, "kns97", datetime(2026, 7, 24), aggregate_code="НА-02")

    assert [aggregate.id for aggregate in obj.aggregates] == ["НА-02"]


def test_telemetry_date_statuses_marks_ready_and_insufficient_days(tmp_path):
    database = _database_with_aggregate(tmp_path)
    ready = datetime(2026, 7, 24)
    incomplete = ready + timedelta(days=1)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 300.0, "кВт"),
        ("q_day", 2400.0, "м³/сут"),
        ("runtime", 24.0, "ч"),
        ("density", 1000.0, "кг/м³"),
    ]:
        database.add_measurement("kns97", "НА-02", ready, metric, value, unit)
    database.add_measurement("kns97", "НА-02", incomplete, "p_in", 1.2, "МПа")

    statuses = telemetry_date_statuses(
        database, "kns97", "НА-02", [date(2026, 7, 24), date(2026, 7, 25)]
    )

    assert statuses == {date(2026, 7, 24): "ready", date(2026, 7, 25): "insufficient"}


def test_telemetry_date_statuses_marks_day_insufficient_without_usable_snapshot(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 210.0, "кВт"),
        ("q_day", 2400.0, "м³/сут"),
        ("runtime", 24.0, "ч"),
        ("density", 1000.0, "кг/м³"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)
    database.add_measurement("kns97", None, start, "p_bg", 10.4, "МПа")

    statuses = telemetry_date_statuses(database, "kns97", "НА-02", [start.date()])

    assert statuses == {start.date(): "insufficient"}


def test_telemetry_day_status_is_the_single_source_for_calendar_status(tmp_path):
    database = _database_with_aggregate(tmp_path)
    start = datetime(2026, 7, 24)
    for metric, value, unit in [
        ("p_in", 1.2, "МПа"),
        ("p_out", 10.4, "МПа"),
        ("power", 300.0, "кВт"),
        ("q_day", 2400.0, "м³/сут"),
        ("runtime", 24.0, "ч"),
        ("density", 1000.0, "кг/м³"),
    ]:
        database.add_measurement("kns97", "НА-02", start, metric, value, unit)

    assert telemetry_day_status(database, "kns97", "НА-02", start.date()) == "ready"
