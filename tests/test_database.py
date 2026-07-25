from datetime import datetime, timedelta

import pytest

from ppd_audit import db as db_module
from ppd_audit.config import project_root
from ppd_audit.db import AuditDatabase, TelemetryMeasurement, default_database_path


def test_schema_persists_object_passport_and_measurement(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_ngdu("Елховнефть")
    db.upsert_plant("kns97", "КНС-97", "Елховнефть", "пресная", "кнс")
    db.upsert_aggregate("kns97", "НА-02", "работа")
    db.add_passport(
        "kns97",
        "НА-02",
        valid_from=datetime(2024, 1, 1),
        pump_model="ЦНС 40-1000(-2)",
        pump_kind="центробежный",
        pump_q_nom=40.0,
        pump_h_nom=1000.0,
        pump_eta_nom=0.52,
        motor_model="ВАО2-450LB-2У2",
        motor_p_nom=400.0,
        motor_eta_nom=0.949,
    )
    db.add_measurement(
        "kns97", "НА-02", datetime(2026, 7, 24, 12), "p_in", 1.2, "МПа"
    )

    measurement = db.measurements("kns97", "НА-02")[0]
    assert measurement["ngdu_name"] == "Елховнефть"
    passport = db.active_passport("kns97", "НА-02", datetime(2026, 7, 24))
    assert passport["pump_model"] == "ЦНС 40-1000(-2)"
    assert measurement["unit"] == "МПа"


def test_measurement_rejects_noncanonical_unit(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("kns10", "КНС-10", "Бавлынефть", "пластовая", "кнс")

    with pytest.raises(ValueError, match="нужна единица МПа"):
        db.add_measurement("kns10", None, datetime(2026, 7, 24), "p_in", 12.0, "атм.")


def test_telemetry_units_are_available_for_data_entry():
    assert db_module.telemetry_units()["p_bg"] == "МПа"
    assert db_module.telemetry_units()["energy"] == "кВт·ч"


def test_annual_runtime_requires_complete_year_of_daily_motohours(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("kns97", "КНС-97", "Елховнефть", "пресная", "кнс")
    db.upsert_aggregate("kns97", "НА-1", "работа")
    end = datetime(2026, 7, 25)
    start = end - timedelta(days=365)

    db.add_measurements(
        iter(
            TelemetryMeasurement("kns97", "НА-1", start + timedelta(days=day), "runtime", 20.0, "ч")
            for day in range(364)
        )
    )
    assert db.annual_runtime("kns97", "НА-1", end) is None

    db.add_measurement("kns97", "НА-1", start + timedelta(days=364), "runtime", 20.0, "ч")
    assert db.annual_runtime("kns97", "НА-1", end) == pytest.approx(7300.0)


def test_plant_list_includes_ngdu(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("kns97", "КНС-97", "Елховнефть", "пресная", "кнс")

    assert db.plants() == [
        {
            "code": "kns97",
            "name": "КНС-97",
            "ngdu_name": "Елховнефть",
            "water_type": "пресная",
            "branch": "кнс",
            "is_example": False,
        }
    ]


def test_clarification_index_tracks_provisional_aggregate_value(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("kns97", "КНС-97", "Елховнефть", "пресная", "кнс")
    db.upsert_aggregate("kns97", "НА-1", "работа")

    db.upsert_clarification(
        "kns97",
        "НА-1",
        field="transmission_eff",
        provisional_value="1.0",
        reason="КПД редуктора не указан на табличке",
    )

    assert db.clarifications("kns97", "НА-1") == [
        {
            "field": "transmission_eff",
            "provisional_value": "1.0",
            "reason": "КПД редуктора не указан на табличке",
            "status": "open",
        }
    ]


def test_open_clarifications_include_object_and_aggregate(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("kns97", "КНС-97", "Елховнефть", "пресная", "кнс")
    db.upsert_aggregate("kns97", "НА-1", "работа")
    db.upsert_clarification(
        "kns97",
        "НА-1",
        field="transmission_eff",
        provisional_value="1.0",
        reason="КПД редуктора не указан на табличке",
    )

    assert db.open_clarifications() == [
        {
            "plant_code": "kns97",
            "plant_name": "КНС-97",
            "aggregate_code": "НА-1",
            "field": "transmission_eff",
            "provisional_value": "1.0",
            "reason": "КПД редуктора не указан на табличке",
        }
    ]


def test_open_clarifications_can_be_filtered_by_object(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    for code, name in (("kns97", "КНС-97"), ("kns54", "КНС-54")):
        db.upsert_plant(code, name, "Елховнефть", "пресная", "кнс")
        db.upsert_aggregate(code, "НА-1", "работа")
        db.upsert_clarification(
            code,
            "НА-1",
            field="t_year",
            provisional_value="8760",
            reason="Нет полного года моточасов",
        )

    assert [item["plant_code"] for item in db.open_clarifications("kns97")] == ["kns97"]


def test_clarification_can_be_resolved(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("kns97", "КНС-97", "Елховнефть", "пресная", "кнс")
    db.upsert_aggregate("kns97", "НА-1", "работа")
    db.upsert_clarification(
        "kns97",
        "НА-1",
        field="t_year",
        provisional_value="8760",
        reason="Нет полного года моточасов",
    )

    db.resolve_clarification("kns97", "НА-1", field="t_year")

    assert db.clarifications("kns97", "НА-1") == []


def test_default_database_is_in_project_root():
    assert default_database_path().name == "telemetry.sqlite"
    assert default_database_path().parent == project_root()


def test_migration_cleans_ngdu_suffix_from_known_name(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("kns10bn", "КНС-10 БН", "Бавлынефть", "пластовая", "кнс")
    with db._connection() as connection:
        connection.execute("PRAGMA user_version = 3")

    db.migrate()

    assert db.plant("kns10bn")["name"] == "КНС-10"


def test_migration_merges_kns97_technical_places_and_renames_pr_aggregate(tmp_path):
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    db.upsert_plant("kns97pren", "КНС-97", "Елховнефть", "пресная", "кнс")
    db.upsert_aggregate("kns97pren", "НА-02", "работа")
    db.upsert_technical_place("kns97pren", "kns97-en", "КНС-97 ЕН")
    db.upsert_aggregate("kns97pren", "НА-03", "работа", technical_place_code="kns97-en")
    db.add_measurement(
        "kns97pren",
        "НА-03",
        datetime(2026, 7, 24),
        "power",
        200.0,
        "кВт",
        technical_place_code="kns97-en",
    )
    with db._connection() as connection:
        connection.execute("PRAGMA user_version = 5")

    db.migrate()

    assert [aggregate["code"] for aggregate in db.aggregates("kns97pren")] == ["НА-2 ПР", "НА-3"]
    assert db.measurements("kns97pren", "НА-3")[0]["value"] == pytest.approx(200.0)
