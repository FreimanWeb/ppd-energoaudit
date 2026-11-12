"""Регистрация новых объектов из config/plants без правок кода."""

from datetime import datetime

import pytest
import yaml

from ppd_audit.db import AuditDatabase
from ppd_audit.db_seed import bootstrap_database
from ppd_audit.services import catalog, monitoring
from ppd_audit.services.audit import run_energy_audit
from ppd_audit.spec import ObjectSpec


def _plant_yaml(plant_id: str, name: str, *, operator_visible: bool | None = None) -> str:
    visibility = (
        f"operator_visible: {str(operator_visible).lower()}\n"
        if operator_visible is not None
        else ""
    )
    return f"""
id: {plant_id}
name: {name}
ngdu: Елховнефть
{visibility}water_type: пресная
branch: кнс
aggregates:
  - id: НА-1
    role: работа
    pump:
      model: ЦНС 60-250
      kind: центробежный
      q_nom: 60
      h_nom: 250
      eta_nom: 0.6
    motor:
      model: ВАО2-450
      p_nom: 200
      eta_nom: 0.94
    regime:
      rho: 1000
      p_in: 1.0
      p_out: 8.0
      p_bg: 7.0
      q_day: 1440
      t: 24
      w: 4000
""".strip()


def _plants_dir(tmp_path):
    plants = tmp_path / "plants"
    plants.mkdir()
    return plants


def test_new_yaml_registers_into_populated_database_on_restart(tmp_path):
    plants = _plants_dir(tmp_path)
    (plants / "kns97.yaml").write_text(_plant_yaml("kns97", "КНС-97"), encoding="utf-8")
    db_path = tmp_path / "audit.sqlite"
    bootstrap_database(db_path, plants)

    (plants / "kns999zz.yaml").write_text(_plant_yaml("kns999zz", "КНС-999"), encoding="utf-8")
    database = bootstrap_database(db_path, plants)

    plant = database.plant("kns999zz")
    assert plant["name"] == "КНС-999"
    assert plant["ngdu_name"] == "Елховнефть"
    assert plant["operator_visible"] is True
    assert [row["code"] for row in database.aggregates("kns999zz")] == ["НА-1"]
    assert (
        database.active_passport("kns999zz", "НА-1", datetime(2026, 1, 1))["pump_model"]
        == "ЦНС 60-250"
    )
    # Повторный запуск идемпотентен и новый объект виден каталогу с честным статусом данных.
    assert bootstrap_database(db_path, plants).plants() == database.plants()
    index = {item["id"]: item for item in catalog.object_index(database)}
    assert index["kns999zz"]["has_telemetry"] is False
    entry = next(
        item
        for item in monitoring.monitoring_objects(database)["objects"]
        if item["code"] == "kns999zz"
    )
    assert entry["data_status"] == "missing"


def test_restart_preserves_operator_edits_of_registered_objects(tmp_path):
    plants = _plants_dir(tmp_path)
    (plants / "kns97.yaml").write_text(_plant_yaml("kns97", "КНС-97"), encoding="utf-8")
    db_path = tmp_path / "audit.sqlite"
    bootstrap_database(db_path, plants)

    database = AuditDatabase(db_path)
    with database._connection() as connection:
        connection.execute(
            "UPDATE plants SET name = ? WHERE code = ?", ("КНС-97 (уточнено)", "kns97")
        )
        connection.execute(
            """UPDATE aggregate_passports SET pump_eta_nom = ?
               WHERE aggregate_id = (
                   SELECT a.id FROM aggregates a
                   JOIN technical_places tp ON tp.id = a.technical_place_id
                   JOIN plants p ON p.id = tp.plant_id
                   WHERE p.code = 'kns97' AND a.code = 'НА-1')""",
            (0.61,),
        )

    restarted = bootstrap_database(db_path, plants)

    assert restarted.plant("kns97")["name"] == "КНС-97 (уточнено)"
    assert restarted.active_passport("kns97", "НА-1", datetime(2026, 1, 1))["pump_eta_nom"] == 0.61


def test_hidden_historical_config_stays_in_database_but_out_of_catalog(tmp_path):
    plants = _plants_dir(tmp_path)
    (plants / "kns85.yaml").write_text(_plant_yaml("kns85", "КНС-85"), encoding="utf-8")
    (plants / "kns14.yaml").write_text(
        _plant_yaml("kns14", "КНС-14", operator_visible=False), encoding="utf-8"
    )
    database = bootstrap_database(tmp_path / "audit.sqlite", plants)

    assert {plant["code"] for plant in database.plants()} == {"kns85", "kns14"}
    assert [item["id"] for item in catalog.object_index(database)] == ["kns85"]
    assert [item["code"] for item in monitoring.monitoring_objects(database)["objects"]] == [
        "kns85"
    ]
    # Явное изменение флага в YAML применяется при следующем запуске.
    (plants / "kns14.yaml").write_text(
        _plant_yaml("kns14", "КНС-14", operator_visible=True), encoding="utf-8"
    )
    database = bootstrap_database(tmp_path / "audit.sqlite", plants)
    assert {item["id"] for item in catalog.object_index(database)} == {"kns85", "kns14"}


def test_invalid_new_config_fails_before_partial_registration(tmp_path):
    plants = _plants_dir(tmp_path)
    (plants / "kns97.yaml").write_text(_plant_yaml("kns97", "КНС-97"), encoding="utf-8")
    db_path = tmp_path / "audit.sqlite"
    bootstrap_database(db_path, plants)

    (plants / "kns01.yaml").write_text(_plant_yaml("kns01", "КНС-01"), encoding="utf-8")
    (plants / "kns02.yaml").write_text(
        _plant_yaml("kns02", "КНС-02").replace("eta_nom: 0.6", "eta_nom: not-a-float"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="kns02"):
        bootstrap_database(db_path, plants)

    codes = {plant["code"] for plant in AuditDatabase(db_path).plants()}
    assert codes == {"kns97"}


def test_new_config_without_ngdu_is_rejected_with_readable_error(tmp_path):
    plants = _plants_dir(tmp_path)
    (plants / "kns03.yaml").write_text("id: kns03\nname: КНС-03\n", encoding="utf-8")

    with pytest.raises(ValueError, match="ngdu"):
        bootstrap_database(tmp_path / "audit.sqlite", plants)

    assert AuditDatabase(tmp_path / "audit.sqlite").plants() == []


def test_new_object_passes_generic_field_trip_audit(tmp_path):
    plants = _plants_dir(tmp_path)
    path = plants / "kns999zz.yaml"
    path.write_text(_plant_yaml("kns999zz", "КНС-999"), encoding="utf-8")

    spec = ObjectSpec(**yaml.safe_load(path.read_text(encoding="utf-8")))
    result = run_energy_audit(spec, "НА-1")

    assert result.regime.q == pytest.approx(60)
    assert result.regime.p_electric > 0
    assert result.decomposition is not None


def test_network_snapshot_resolves_by_convention_for_any_object(tmp_path):
    import json

    from ppd_audit.config import project_root
    from ppd_audit.services.armits_data import load_network

    armits = project_root() / "data" / "armits"
    target = armits / "kns999zz.yaml".replace(".yaml", ".json")
    load_network.cache_clear()
    try:
        target.write_text(json.dumps({"object_id": "kns999zz", "wells": []}), encoding="utf-8")
        load_network.cache_clear()
        assert load_network("kns999zz") == {"object_id": "kns999zz", "wells": []}
        assert load_network("../outside") is None
    finally:
        target.unlink(missing_ok=True)
        load_network.cache_clear()
