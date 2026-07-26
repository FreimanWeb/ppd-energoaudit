from datetime import date, datetime, timedelta

import pytest

from ppd_audit.db import AuditDatabase
from ppd_audit.services.telemetry_audit import (
    build_regime,
    object_from_database,
    run_snapshot_audit,
    run_telemetry_audit,
    telemetry_date_statuses,
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

    assert regime.p_in == pytest.approx(13 / 3)
    assert regime.p_out == pytest.approx(80 / 3)
    assert regime.p_electric == pytest.approx(300.0)


def test_build_regime_rejects_pressure_pair_far_from_positive_power(tmp_path):
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

    with pytest.raises(ValueError, match="нет согласованной пары p_вх/p_вых"):
        build_regime(database, "kns97", "НА-02", start, start + timedelta(days=1))


def test_build_regime_rejects_insufficient_pressure_coverage_of_operating_power(tmp_path):
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

    with pytest.raises(ValueError, match="давление покрывает только 1 из 2"):
        build_regime(database, "kns97", "НА-02", start, start + timedelta(days=1))


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


def test_snapshot_rejects_pressure_pair_more_than_five_minutes_from_power(tmp_path):
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

    with pytest.raises(ValueError, match="нет согласованной пары p_вх/p_вых"):
        build_regime(
            database,
            "kns97",
            "НА-02",
            start,
            start + timedelta(days=1),
            require_daily_pressure_coverage=False,
        )


def test_snapshot_rejects_fast_pressure_transition(tmp_path):
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

    with pytest.raises(ValueError, match="нет согласованной пары p_вх/p_вых"):
        build_regime(
            database,
            "kns97",
            "НА-02",
            start,
            start + timedelta(days=1),
            require_daily_pressure_coverage=False,
        )


def test_telemetry_snapshots_keep_measurement_timestamps_and_gaps(tmp_path):
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
    assert snapshots[0].timestamp == start
    assert snapshots[0].power_kw == pytest.approx(210.0)
    assert snapshots[0].power_gap == timedelta(minutes=4)
    assert snapshots[0].p_bg_mpa == pytest.approx(9.8)
    assert snapshots[0].p_bg_gap == timedelta(minutes=2)


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
    database.add_measurement("kns97", "НА-02", start + timedelta(minutes=4), "power", 210.0, "кВт")

    snapshot = run_snapshot_audit(
        database, "kns97", "НА-02", start, start + timedelta(days=1), start
    )

    assert snapshot.audit.regime.p_in == pytest.approx(1.2)
    assert snapshot.audit.regime.p_out == pytest.approx(10.4)
    assert snapshot.uses_daily_flow is True
    assert snapshot.uses_daily_power is True
    assert snapshot.annual_runtime_is_assumed is True


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

    statuses = telemetry_date_statuses(database, "kns97", "НА-02", [start.date()])

    assert statuses == {start.date(): "snapshot"}


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
        ("power", 210.0, "кВт"),
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
