"""Каталог объектов и подготовка данных для API и frontend."""

from __future__ import annotations

import os
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from ..core.audit import AuditResult
from ..db import AuditDatabase, default_database_path
from ..db_seed import (
    ScadaSeedResult,
    bootstrap_database,
    seed_telemetry_from_excel,
    seed_telemetry_from_scada,
)
from ..ingest.crm_forecast import CRM_DIRNAME
from ..ingest.downtime import DOWNTIME_DIRNAME
from ..services.audit import run_energy_audit
from ..spec import ObjectSpec, load_object_spec
from .armits_data import load_network


def prepare_database(root: Path, path: Path | None = None):
    """Подготовить БД приложения: справочники, выгрузки АСУ ТП, примеры.

    Повторный вызов дешёвый: справочники пишутся только при расхождении,
    выгрузки — только если в каталоге появились новые файлы. Импорт можно
    отключить переменными ``PPD_SKIP_SCADA_TELEMETRY`` и
    ``PPD_SKIP_EXAMPLE_TELEMETRY`` (изолированные тесты).
    """
    from ..db_seed import DEFAULT_SCADA_DIRNAME, DEFAULT_TELEMETRY_DIRNAME

    path = path or default_database_path()
    sources = source_paths(root)
    telemetry_dir = root / "data" / DEFAULT_TELEMETRY_DIRNAME
    scada_dir = Path(os.getenv("PPD_SCADA_DIR", telemetry_dir / DEFAULT_SCADA_DIRNAME))
    db = bootstrap_database(path, root / "config" / "plants", include_demo=True)
    scada = (
        seed_telemetry_from_scada(db, scada_dir, sources["scada_tags"], sources["exports"])
        if os.getenv("PPD_SKIP_SCADA_TELEMETRY") != "1"
        else ScadaSeedResult(scada_dir, 0, 0, reason="импорт выгрузок отключён")
    )
    seed = seed_telemetry_from_excel(
        db, telemetry_dir, include_examples=os.getenv("PPD_SKIP_EXAMPLE_TELEMETRY") != "1"
    )
    return path, seed, scada


def list_object_ids(
    plants_dir: Path,
) -> list[str]:
    """Операторские объекты из config/plants/*.yaml, для которых грузится спец."""
    ids = []
    for p in sorted(plants_dir.glob("*.yaml")):
        try:
            spec = load_object_spec(p.stem)
        except Exception:
            continue
        if spec.is_example or spec.ngdu is None or not spec.operator_visible:
            continue
        ids.append(p.stem)
    return ids


def operator_visible_in_catalog(record: dict) -> bool:
    """Политика каталога операторов: явно скрытый конфиг и неявные примеры прочь."""
    from .demo import DEMO_OBJECT_ID

    return bool(record["operator_visible"]) and (
        not record["is_example"] or record["code"] == DEMO_OBJECT_ID
    )


def get_field_trip_audit(
    object_id: str, aggregate_id: str, *, database: AuditDatabase | None = None
) -> tuple[ObjectSpec, AuditResult]:
    """Выездной замер с плотностью, доступной на дату измерения."""
    obj = load_object_spec(object_id)
    db = database if database is not None else AuditDatabase(default_database_path())
    obj = with_confirmed_density(obj, db)
    return obj, run_energy_audit(obj, aggregate_id)


def with_confirmed_density(obj: ObjectSpec, database: AuditDatabase) -> ObjectSpec:
    today = datetime.now(ZoneInfo("Europe/Moscow")).date()
    result = obj
    for index, aggregate in enumerate(obj.aggregates):
        if aggregate.regime is None:
            continue
        at = aggregate.regime.measured_at or today
        reading = database.plant_density_default(obj.id, at)
        if reading is None or aggregate.regime.rho == reading["density_kgm3"]:
            continue
        if result is obj:
            result = obj.model_copy(deep=True)
        result.aggregates[index].regime.rho = reading["density_kgm3"]
    return result


def object_index(
    database: AuditDatabase,
) -> list[dict]:
    """Список объектов с метаданными для выбора/фильтра."""
    db = database
    out = []
    for record in db.plants(include_examples=True):
        if not operator_visible_in_catalog(record):
            continue
        oid = record["code"]
        aggregates = db.aggregates(oid)
        out.append({
            "id": oid,
            "name": record["name"],
            "water": record["water_type"],
            "branch": record["branch"],
            "n_agg": len(aggregates),
            "aggregate_ids": [aggregate["code"] for aggregate in aggregates],
            "ngdu": record["ngdu_name"],
            "is_example": record["is_example"],
            "has_network": load_network(oid) is not None,
            "has_telemetry": any(
                db.telemetry_dates(oid, aggregate["code"]) for aggregate in aggregates
            ),
        })
    return out


def get_topology(topology_dir: Path, object_id: str) -> dict | None:
    """As-built технологическая схема объекта (config/topology/<id>.yaml), если задана.

    Отдельный конфиг (узлы/трубопроводы) — не часть core-спеки, поэтому добавление
    топологии не влияет на расчётное ядро и его тесты.
    """
    import yaml

    p = topology_dir / f"{object_id}.yaml"
    if not p.exists():
        return None
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def tariff(at: date | None = None, *, database: AuditDatabase | None = None) -> dict:
    at = at if at is not None else datetime.now(ZoneInfo("Europe/Moscow")).date()
    db = database if database is not None else AuditDatabase(default_database_path())
    reading = db.electricity_tariff(at)
    if reading is None:
        raise ValueError("В БД отсутствуют тарифы электроэнергии")
    warning = None
    if not reading["valid_from"] <= at.isoformat() <= reading["valid_to"]:
        warning = (
            f"Для даты {at.isoformat()} тариф не задан. Применён ближайший тариф "
            f"{reading['rub_per_kwh']:g} ₽/кВт·ч за период "
            f"{reading['valid_from']} — {reading['valid_to']}."
        )
    return {**reading, "warning": warning}


def open_clarifications(database: AuditDatabase, object_id: str, aggregate_id: str) -> list[dict]:
    return database.clarifications(object_id, aggregate_id)


def aggregate_index(database: AuditDatabase, object_id: str) -> list[dict]:
    """Состав агрегатов; отсутствие паспорта не скрывает сам агрегат."""
    result = []
    for aggregate in database.aggregates(object_id):
        days = database.telemetry_dates(object_id, aggregate["code"])
        at = datetime.combine(days[-1], time.min) if days else datetime.now()
        try:
            model = database.active_passport(object_id, aggregate["code"], at)["pump_model"]
        except KeyError:
            model = None
        result.append({**aggregate, "pump_model": model, "has_telemetry": bool(days)})
    return result


def source_paths(root: Path) -> dict[str, Path]:
    """Пути внешних источников; overrides позволяют изолировать import/preview."""
    from ..db_seed import SCADA_TAGS_CONFIG

    return {
        "crm": Path(os.getenv("PPD_CRM_DIR", root / "data" / CRM_DIRNAME)),
        "downtime": Path(os.getenv("PPD_DOWNTIME_DIR", root / "data" / DOWNTIME_DIRNAME)),
        "scada_tags": Path(os.getenv("PPD_SCADA_TAGS_PATH", root / "config" / SCADA_TAGS_CONFIG)),
        "network": Path(os.getenv("PPD_NETWORK_DIR", root / "data" / "network")),
        "exports": Path(os.getenv("PPD_EXPORTS_DIR", root / "data" / "telemetry" / "exports")),
        "network_config": Path(os.getenv("PPD_NETWORK_CONFIG", root / "config" / "network.yaml")),
    }
