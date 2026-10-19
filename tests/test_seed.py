from datetime import datetime

from ppd_audit.db import AuditDatabase
from ppd_audit.db_seed import bootstrap_database, seed_passports


def test_seed_persists_ngdu_and_passport(tmp_path):
    plants = tmp_path / "plants"
    plants.mkdir()
    (plants / "kns97.yaml").write_text(
        """
id: kns97
name: КНС-97
ngdu: Елховнефть
water_type: пресная
branch: кнс
aggregates:
  - id: НА-02
    role: работа
    pump:
      model: ЦНС 40-1000(-2)
      kind: центробежный
      q_nom: 40
      h_nom: 1000
      eta_nom: 0.52
    motor:
      model: ВАО2-450LB-2У2
      p_nom: 400
      eta_nom: 0.949
""".strip(),
        encoding="utf-8",
    )
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()

    seeded = seed_passports(db, plants, valid_from=datetime(2024, 1, 1))

    assert seeded == ["kns97"]
    assert db.plants()[0]["ngdu_name"] == "Елховнефть"
    assert db.active_passport("kns97", "НА-02", datetime(2026, 1, 1))["motor_p_nom"] == 400


def test_bootstrap_seeds_empty_database_once(tmp_path):
    plants = tmp_path / "plants"
    plants.mkdir()
    (plants / "kns97.yaml").write_text(
        "id: kns97\nname: КНС-97\nngdu: Елховнефть\nwater_type: пресная\nbranch: кнс\n",
        encoding="utf-8",
    )

    db = bootstrap_database(tmp_path / "audit.sqlite", plants)

    assert db.plants()[0]["code"] == "kns97"


def test_seed_updates_extended_passport_fields(tmp_path):
    plants = tmp_path / "plants"
    plants.mkdir()
    passport = plants / "kns97.yaml"
    passport.write_text(
        """
id: kns97
name: КНС-97
ngdu: Елховнефть
water_type: пресная
branch: кнс
aggregates:
  - id: НА-1
    pump:
      model: СТ-А НПЖ
      kind: объёмный
      power_nom: 320
      n_rpm: 300
    motor:
      model: A355SMC4У3
      p_nom: 355
      eta_nom: 0.959
      n_rpm: 1480
    transmission:
      model: СТ-А Ц-1-280-4,55-12-1
      ratio: 4.5
      efficiency: 0.9
    clarifications:
      - field: transmission_eff
        value: 0.9
        reason: КПД редуктора требует подтверждения паспортом
""".strip(),
        encoding="utf-8",
    )
    db = AuditDatabase(tmp_path / "audit.sqlite")
    db.migrate()
    seed_passports(db, plants, valid_from=datetime(2024, 1, 1))

    passport.write_text(
        passport
        .read_text(encoding="utf-8")
        .replace("power_nom: 320", "power_nom: 340")
        .replace("n_rpm: 300", "n_rpm: 308", 1)
        .replace("n_rpm: 1480", "n_rpm: 1488")
        .replace("ratio: 4.5", "ratio: 4.55")
        .replace("efficiency: 0.9", "efficiency: 0.92"),
        encoding="utf-8",
    )
    seed_passports(db, plants, valid_from=datetime(2024, 1, 1))

    seeded = db.active_passport("kns97", "НА-1", datetime(2026, 1, 1))

    assert seeded["pump_power_nom"] == 340
    assert seeded["pump_n_rpm"] == 308
    assert seeded["motor_n_rpm"] == 1488
    assert seeded["transmission_model"] == "СТ-А Ц-1-280-4,55-12-1"
    assert seeded["transmission_ratio"] == 4.55
    assert seeded["transmission_eff"] == 0.92
    assert db.clarifications("kns97", "НА-1")[0]["field"] == "transmission_eff"


def test_refined_density_and_runtime_reach_an_existing_database(tmp_path):
    import yaml

    from ppd_audit.db_seed import sync_reference_values

    plants = tmp_path / "plants"
    plants.mkdir()
    raw = {
        "id": "opu",
        "name": "КНС-ОПУ",
        "ngdu": "Джалильнефть",
        "aggregates": [{"id": "НА-1", "regime": {"rho": 1123.0, "p_in": 1, "p_out": 9}}],
    }
    (plants / "opu.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    database = bootstrap_database(tmp_path / "audit.sqlite", plants)
    assert database.plant("opu")["default_density"] == 1123.0

    raw["density"] = 1142.0
    raw["aggregates"][0]["runtime_total_h"] = 300.0
    (plants / "opu.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    sync_reference_values(database, plants)

    assert database.plant("opu")["default_density"] == 1142.0
    assert database.aggregate("opu", "НА-1")["runtime_total_h"] == 300.0


def test_passports_bring_density_and_runtime_into_a_new_database(tmp_path):
    from ppd_audit.config import project_root

    database = bootstrap_database(tmp_path / "audit.sqlite", project_root() / "config" / "plants")

    assert database.plant("knsopu")["default_density"] == 1142.0
    assert database.aggregate("kns54an", "НА-1")["runtime_total_h"] == 13500.0
    assert database.aggregate("kns97pren", "НА-2 ПР")["runtime_total_h"] == 43846.0
