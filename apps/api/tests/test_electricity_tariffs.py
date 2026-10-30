import sqlite3
from datetime import date

import pytest

from ppd_audit.db import AuditDatabase
from ppd_audit.services.catalog import tariff


def test_v10_prices_become_periods_without_replacing_corrections(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("test", "Test", "NGDU", "пресная", "кнс")
    with sqlite3.connect(db.path) as connection:
        connection.execute("DROP TABLE electricity_tariffs")
        connection.execute(
            "CREATE TABLE electricity_tariffs "
            "(year INTEGER PRIMARY KEY, rub_per_kwh REAL, source TEXT)"
        )
        connection.execute("INSERT INTO electricity_tariffs VALUES (2026, 6.25, 'Correction')")
        connection.execute("PRAGMA user_version = 10")
    db.migrate()
    db.migrate()
    assert db.plant("test")["name"] == "Test"
    row = db.electricity_tariff(date(2026, 7, 1))
    assert row == {
        "valid_from": "2026-01-01",
        "valid_to": "2026-12-31",
        "rub_per_kwh": 6.25,
        "source": "Correction",
    }
    assert db.electricity_tariff(date(2025, 7, 1))["rub_per_kwh"] == 4.68


@pytest.mark.parametrize(
    "day,price,warning",
    [
        ("2024-12-31", 4.68, True),
        ("2025-01-01", 4.68, False),
        ("2025-12-31", 4.68, False),
        ("2026-01-01", 5.17, False),
        ("2026-12-31", 5.17, False),
        ("2027-01-01", 5.17, True),
    ],
)
def test_inclusive_dates_and_nearest_period_warning(tmp_path, day, price, warning):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    selection = tariff(date.fromisoformat(day), database=db)
    assert selection["rub_per_kwh"] == price
    assert bool(selection["warning"]) == warning
    if warning:
        assert day in selection["warning"]
        assert selection["valid_from"] in selection["warning"]
        assert selection["valid_to"] in selection["warning"]


def test_gap_uses_nearest_boundary_and_prefers_later_period_on_tie(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    with db._connection() as connection:
        connection.execute("DELETE FROM electricity_tariffs")
    db.upsert_electricity_tariff(date(2026, 1, 1), date(2026, 1, 10), 4, source="A")
    db.upsert_electricity_tariff(date(2026, 1, 20), date(2026, 1, 31), 5, source="B")
    assert tariff(date(2026, 1, 14), database=db)["rub_per_kwh"] == 4
    assert tariff(date(2026, 1, 15), database=db)["rub_per_kwh"] == 5
    assert tariff(date(2026, 1, 16), database=db)["rub_per_kwh"] == 5
    with pytest.raises(ValueError, match="пересека"):
        db.upsert_electricity_tariff(date(2026, 1, 10), date(2026, 1, 19), 6, source="Overlap")
    with pytest.raises(ValueError, match="пересека"):
        db.upsert_electricity_tariff(
            date(2026, 1, 1), date(2026, 1, 20), 6, source="Overlap update"
        )
    assert tariff(date(2026, 1, 1), database=db)["rub_per_kwh"] == 4


@pytest.mark.parametrize("price", [0, -1, float("nan"), float("inf")])
def test_invalid_price_cannot_replace_confirmed_tariff(tmp_path, price):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    with pytest.raises(ValueError):
        db.upsert_electricity_tariff(date(2026, 1, 1), date(2026, 12, 31), price, source="Invalid")
    assert db.electricity_tariff(date(2026, 1, 1))["rub_per_kwh"] == 5.17


def test_invalid_period_and_empty_table(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    with pytest.raises(ValueError):
        db.upsert_electricity_tariff(date(2027, 2, 1), date(2027, 1, 1), 5, source="Invalid")
    with db._connection() as connection:
        connection.execute("DELETE FROM electricity_tariffs")
    with pytest.raises(ValueError, match="отсутствуют тарифы"):
        tariff(date(2026, 1, 1), database=db)
