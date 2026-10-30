from datetime import date, datetime

from ppd_audit.db import SCHEMA_VERSION, AuditDatabase


def _database(tmp_path):
    database = AuditDatabase(tmp_path / "merge.sqlite")
    database.migrate()
    database.upsert_plant("station", "Station", "NGDU", "пресная", "кнс")
    database.upsert_aggregate("station", "pump", "работа")
    database.add_measurement("station", "pump", datetime(2026, 10, 19), "p_in", 0.5, "МПа")
    return database


def test_upgrades_remote_v10_without_tariffs_and_keeps_runtime(tmp_path):
    database = _database(tmp_path)
    database.set_runtime_total("station", "pump", 1234)
    with database._connection() as connection:
        for table in ("electricity_tariffs", "well_measurements", "plant_density_defaults"):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("PRAGMA user_version = 10")

    database.migrate()
    database.migrate()

    assert database.aggregates("station")[0]["runtime_total_h"] == 1234
    assert database.electricity_tariff(date(2026, 1, 1))["rub_per_kwh"] == 5.17
    assert len(database.measurements("station", "pump")) == 1
    assert database.wells("station") == []
    with database._connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_upgrades_local_v12_without_runtime_and_keeps_custom_tariff(tmp_path):
    database = _database(tmp_path)
    database.upsert_electricity_tariff(
        date(2026, 1, 1), date(2026, 12, 31), 9.99, source="Custom tariff"
    )
    with database._connection() as connection:
        connection.execute("ALTER TABLE aggregates DROP COLUMN runtime_total_h")
        connection.execute("PRAGMA user_version = 12")

    database.migrate()
    database.migrate()

    assert database.aggregates("station")[0]["runtime_total_h"] is None
    assert database.electricity_tariff(date(2026, 1, 1))["rub_per_kwh"] == 9.99
    assert len(database.measurements("station", "pump")) == 1
    with database._connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
