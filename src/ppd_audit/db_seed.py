"""Первичное заполнение SQLite паспортами из временных YAML-конфигов."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml

from .db import AuditDatabase


def bootstrap_database(path: Path, plants_dir: Path) -> AuditDatabase:
    """Создать локальную БД и заполнить её паспортами только при первом запуске."""
    database = AuditDatabase(path)
    database.migrate()
    if not database.plants(include_examples=True):
        seed_passports(database, plants_dir, valid_from=datetime(1970, 1, 1))
    return database


def seed_passports(
    database: AuditDatabase, plants_dir: Path, *, valid_from: datetime,
) -> list[str]:
    """Идемпотентно перенести YAML-паспорта в БД.

    YAML применяется только при первоначальном заполнении: runtime читает БД.
    Объект без подтверждённого НГДУ не переносится, чтобы не создавать ложную связь.
    """
    seeded = []
    for path in sorted(plants_dir.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        ngdu = raw.get("ngdu")
        if not ngdu:
            continue
        database.upsert_plant(
            raw["id"],
            raw["name"],
            ngdu,
            raw.get("water_type", "пресная"),
            raw.get("branch", "кнс"),
            is_example=raw.get("is_example", False),
            default_density=_first_regime_value(raw, "rho"),
            default_viscosity=_first_regime_value(raw, "nu"),
        )
        for aggregate in raw.get("aggregates", []):
            database.upsert_aggregate(raw["id"], aggregate["id"], aggregate.get("role", "работа"))
            pump = aggregate.get("pump", {})
            motor = aggregate.get("motor", {})
            transmission = aggregate.get("transmission", {})
            database.add_passport(
                raw["id"],
                aggregate["id"],
                valid_from=valid_from,
                pump_model=pump.get("model", ""),
                pump_kind=pump.get("kind", "центробежный"),
                pump_q_nom=pump.get("q_nom"),
                pump_h_nom=pump.get("h_nom"),
                pump_eta_nom=pump.get("eta_nom"),
                motor_model=motor.get("model", ""),
                motor_p_nom=motor.get("p_nom"),
                motor_eta_nom=motor.get("eta_nom"),
                pump_power_nom=pump.get("power_nom"),
                pump_n_rpm=pump.get("n_rpm"),
                pump_curve_qh_json=json.dumps(pump.get("curve_qh", [])),
                pump_curve_qeta_json=json.dumps(pump.get("curve_qeta", [])),
                motor_synchronous=motor.get("synchronous", False),
                motor_cos_phi=motor.get("cos_phi"),
                motor_voltage_kv=motor.get("voltage_kv"),
                motor_i_nom=motor.get("i_nom"),
                motor_n_rpm=motor.get("n_rpm"),
                transmission_model=transmission.get("model"),
                transmission_ratio=transmission.get("ratio"),
                transmission_eff=transmission.get("efficiency", 1.0),
                vfd=aggregate.get("vfd", False),
            )
            for clarification in aggregate.get("clarifications", []):
                database.upsert_clarification(
                    raw["id"],
                    aggregate["id"],
                    field=clarification["field"],
                    provisional_value=str(clarification["value"]),
                    reason=clarification["reason"],
                )
        seeded.append(raw["id"])
    return seeded


def _first_regime_value(raw: dict, field: str) -> float | None:
    for aggregate in raw.get("aggregates", []):
        value = aggregate.get("regime", {}).get(field)
        if value is not None:
            return float(value)
    return None
