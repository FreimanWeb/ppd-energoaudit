from datetime import datetime, timedelta

import pytest
from openpyxl import Workbook

from ppd_audit.core.audit import audit_aggregate
from ppd_audit.db import AuditDatabase
from ppd_audit.db_import import import_excel_telemetry
from ppd_audit.services.network_view import time_weighted_median
from ppd_audit.services.telemetry_audit import telemetry_snapshots
from ppd_audit.spec import AggregateSpec, MotorSpec, PumpSpec, RegimeMeasurement


@pytest.fixture
def database(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("kns54an", "КНС", "НГДУ", "пресная", "кнс")
    db.upsert_aggregate("kns54an", "НА-1", "работа")
    return db


def test_reported_daily_power_cannot_overwrite_an_instantaneous_measurement(database, tmp_path):
    stamp = datetime(2026, 9, 1)
    instant = Workbook()
    instant.active.append(["Дата", "Акт.прямая мощность, кВт"])
    instant.active.append([stamp, 320.0])
    instant.save(tmp_path / "КНС-54 НА-1 мощность.xlsx")
    daily = Workbook()
    daily.active.title = "r1020"
    daily.active.append(["Дата", "Тех. место", "Мощность (кВт)"])
    daily.active.append([stamp, "НА-1", 190.0])
    daily.save(tmp_path / "КНС-54 проток.xlsx")

    import_excel_telemetry(database, tmp_path)
    records = database.measurements("kns54an", "НА-1")
    values = {row["metric"]: row["value"] for row in records}
    assert values["power"] == 320.0
    assert values["power_daily_reported"] == 190.0


def test_station_pressure_is_scoped_to_the_aggregate_hydraulic_group(database):
    stamp = datetime(2026, 9, 1)
    for group, aggregate, pressure in [("ordinary", "A", 7.0), ("fresh", "B", 4.0)]:
        database.upsert_technical_place("kns54an", group, group)
        database.upsert_aggregate("kns54an", aggregate, "работа", technical_place_code=group)
        database.add_measurement(
            "kns54an", None, stamp, "p_bg", pressure, "МПа", technical_place_code=group
        )
    rows = database.measurements_in_window(
        "kns54an",
        "B",
        stamp,
        stamp + timedelta(days=1),
        technical_place_code="fresh",
        include_station=True,
    )
    assert [row["value"] for row in rows if row["metric"] == "p_bg"] == [4.0]


def test_unconfirmed_quality_cannot_supply_a_calculable_snapshot(database):
    stamp = datetime(2026, 9, 1)
    for metric, value, unit in [("p_in", 1.0, "МПа"), ("p_out", 11.0, "МПа")]:
        database.add_measurement("kns54an", "НА-1", stamp, metric, value, unit)
    database.add_measurement("kns54an", "НА-1", stamp, "power", 200.0, "кВт", quality="unconfirmed")
    assert telemetry_snapshots(database, "kns54an", "НА-1", stamp, stamp + timedelta(days=1)) == []


def test_missing_passport_efficiency_preserves_facts_without_nominal_estimates():
    aggregate = AggregateSpec(
        id="A",
        pump=PumpSpec(),
        motor=MotorSpec(),
        regime=RegimeMeasurement(
            rho=1000.0,
            p_in=1.0,
            p_out=11.0,
            q_fact=36.0,
            p_electric=200.0,
        ),
    )
    audit = audit_aggregate(aggregate)
    assert audit.regime.p_hydraulic == pytest.approx(100.0)
    assert audit.regime.eta_unit == pytest.approx(0.5)
    assert audit.sec_fact == pytest.approx(200.0 / 36.0)
    assert audit.regime.eta_nom is None
    assert audit.sec_calc is None
    assert audit.dw_efficiency is None
    assert audit.decomposition is None


def test_unknown_station_quality_is_a_gap_not_another_pressure(database):
    stamp = datetime(2026, 9, 1)
    database.add_measurement("kns54an", None, stamp, "p_bg", 7.0, "МПа")
    database.add_measurement(
        "kns54an", None, stamp + timedelta(hours=10), "p_bg", 9.0, "МПа", quality="0.0"
    )
    events = database.station_metric_events("kns54an", "p_bg", stamp, stamp + timedelta(days=1))
    assert time_weighted_median(events, stamp, stamp + timedelta(days=1)) is None


def test_source_number_migration_preserves_equipment_history(database):
    stamp = datetime(2026, 9, 1)
    database.upsert_plant("kns14an", "КНС-14", "НГДУ", "пресная", "кнс")
    for code, model in [("НА-1", "ГНУ REDA 1000-1300"), ("НА-2", "СИН61.02.100")]:
        database.upsert_aggregate("kns14an", code, "работа")
        database.add_passport(
            "kns14an",
            code,
            valid_from=stamp,
            pump_model=model,
            pump_kind="центробежный",
            pump_q_nom=None,
            pump_h_nom=None,
            pump_eta_nom=None,
            motor_model="",
            motor_p_nom=None,
            motor_eta_nom=None,
        )
    database.add_measurement("kns14an", "НА-1", stamp, "power", 200.0, "кВт")
    with database._connection() as connection:
        connection.execute("PRAGMA user_version = 14")
    database.migrate()
    database.migrate()
    assert database.active_passport("kns14an", "НА-2", stamp)["pump_model"] == "ГНУ REDA 1000-1300"
    assert database.measurements("kns14an", "НА-2")[0]["value"] == 200.0


def test_minute_header_does_not_supply_confirmed_operating_hours(database, tmp_path):
    from ppd_audit.services.telemetry_acceptance import acceptance_report
    from ppd_audit.services.telemetry_audit import build_regime

    stamp = datetime(2026, 9, 1)
    book = Workbook()
    book.active.title = "r1020"
    book.active.append(["Дата", "Тех. место", "Моточасы (мин)", "Энергия (кВт-ч)", "Расход (м3)"])
    book.active.append([stamp, "НА-1", 12.0, 2400.0, 1200.0])
    book.save(tmp_path / "КНС-54 проток.xlsx")
    import_excel_telemetry(database, tmp_path)
    for metric, value, unit in [
        ("p_in", 1.0, "МПа"),
        ("p_out", 11.0, "МПа"),
        ("power", 200.0, "кВт"),
        ("density", 1000.0, "кг/м³"),
    ]:
        database.add_measurement("kns54an", "НА-1", stamp, metric, value, unit)
    regime = build_regime(database, "kns54an", "НА-1", stamp, stamp + timedelta(days=1))
    assert regime.t is None
    with pytest.raises(ValueError, match="подачи"):
        regime.flow()
    report = acceptance_report(database.measurements("kns54an", "НА-1"))
    assert report["calculations"][0]["status"] == "available"


def test_unconfirmed_runtime_cannot_become_a_confirmed_annual_total(database):
    from ppd_audit.db import TelemetryMeasurement

    start = datetime(2025, 1, 1)
    database.add_measurements(
        TelemetryMeasurement(
            "kns54an",
            "НА-1",
            start + timedelta(days=day),
            "runtime",
            1.0,
            "ч",
            quality="unit_unconfirmed" if day == 100 else None,
        )
        for day in range(365)
    )
    assert database.annual_runtime("kns54an", "НА-1", start + timedelta(days=365)) is None


def test_distinct_pressure_columns_cannot_overwrite_each_other(database, tmp_path):
    book = Workbook()
    book.active.append([
        "Дата",
        "Давление на выкиде",
        "Давление на приёме",
        "Датчик давления на выкиде",
    ])
    book.active.append([datetime(2026, 4, 24), 132.0, 25.8, 2.5284])
    book.save(tmp_path / "КНС-54 НА-1 давления.xlsx")
    import_excel_telemetry(database, tmp_path)
    rows = {row["metric"]: row for row in database.measurements("kns54an", "НА-1")}
    assert rows["p_out"]["value"] == pytest.approx(132 * 0.0980665)
    assert rows["pressure_unassigned"]["value"] == 2.5284
    assert rows["pressure_unassigned"]["unit"] == "не подтверждена"


@pytest.mark.parametrize(
    "places,aggregates",
    [
        ({}, [{"id": "A", "technical_place_code": "missing"}]),
        ({"other": "Другой контур"}, [{"id": "A"}, {"id": "A", "technical_place_code": "other"}]),
    ],
)
def test_invalid_group_bindings_cannot_partially_register_an_object(
    database,
    tmp_path,
    places,
    aggregates,
):
    import yaml

    from ppd_audit.db_seed import seed_passports

    directory = tmp_path / "plants"
    directory.mkdir()
    (directory / "new-site.yaml").write_text(
        yaml.safe_dump({
            "id": "new-site",
            "name": "Новая КНС",
            "ngdu": "НГДУ",
            "technical_places": places,
            "aggregates": aggregates,
        }),
        encoding="utf-8",
    )
    with pytest.raises((KeyError, ValueError)):
        seed_passports(database, directory, valid_from=datetime(2026, 1, 1))
    assert "new-site" not in {plant["code"] for plant in database.plants()}


@pytest.mark.parametrize("early_flow", [18.0, 0.0])
def test_snapshot_cannot_use_a_later_flow_measurement(database, early_flow):
    from ppd_audit.services.telemetry_audit import run_snapshot_audit

    stamp = datetime(2026, 9, 1)
    database.add_passport(
        "kns54an",
        "НА-1",
        valid_from=stamp,
        pump_model="",
        pump_kind="центробежный",
        pump_q_nom=None,
        pump_h_nom=None,
        pump_eta_nom=None,
        motor_model="",
        motor_p_nom=None,
        motor_eta_nom=None,
    )
    for metric, value, unit in [
        ("p_in", 1.0, "МПа"),
        ("p_out", 11.0, "МПа"),
        ("power", 200.0, "кВт"),
        ("density", 1000.0, "кг/м³"),
    ]:
        database.add_measurement("kns54an", "НА-1", stamp, metric, value, unit)
    database.add_measurement(
        "kns54an",
        "НА-1",
        stamp,
        "flow_rate",
        early_flow,
        "м³/ч",
        source_file="early-flow.csv",
    )
    database.add_measurement(
        "kns54an",
        "НА-1",
        stamp + timedelta(hours=12),
        "flow_rate",
        72.0,
        "м³/ч",
        source_file="later-flow.csv",
    )
    if early_flow == 0:
        with pytest.raises(ValueError):
            run_snapshot_audit(database, "kns54an", "НА-1", stamp, stamp + timedelta(days=1), stamp)
    else:
        result = run_snapshot_audit(
            database, "kns54an", "НА-1", stamp, stamp + timedelta(days=1), stamp
        )
        assert result.audit.regime.q == 18.0
        assert result.audit.regime.eta_unit == pytest.approx(0.25)
        assert result.sources["Q"] == "early-flow.csv"


def test_bad_flow_samples_are_not_integrated_as_a_coarser_valid_series():
    from ppd_audit.services.telemetry_audit import _integrated_flow_rate

    stamp = datetime(2026, 9, 1)
    rows = [
        {
            "timestamp": (stamp + timedelta(minutes=minute)).isoformat(),
            "metric": "flow_rate",
            "is_station": False,
            "value": 100.0,
            "unit": "м³/ч",
            "quality": "unconfirmed" if minute % 60 else None,
        }
        for minute in (0, 30, 60, 90)
    ]
    assert _integrated_flow_rate(stamp, stamp + timedelta(hours=2), rows) is None
