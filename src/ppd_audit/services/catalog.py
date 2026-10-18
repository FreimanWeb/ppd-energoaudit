"""Каталог объектов и подготовка данных, общие для API и Streamlit."""

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
from ..verify.runner import run_verification


def bootstrap_app_data(root: Path, telemetry_dir: Path, scada_dir: Path, scada_tags: Path):
    """Разовая подготовка БД. Возвращает путь, а не объект базы.

    Объект здесь кэшировать нельзя: ``st.cache_resource`` переживает
    обновление кода, и после деплоя в кэше остаётся экземпляр, собранный по
    прежней версии класса — новые методы у него отсутствуют, и приложение
    падает с AttributeError до перезапуска. Путь же переживает обновление
    безболезненно, а собрать ``AuditDatabase`` заново стоит один вызов
    конструктора: соединение открывается на каждую операцию отдельно.
    """
    path = default_database_path()
    db = bootstrap_database(path, root / "config" / "plants", include_demo=True)
    scada = (
        seed_telemetry_from_scada(db, scada_dir, scada_tags)
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
    """Все объекты из config/plants/*.yaml, для которых грузится спец."""
    ids = []
    for p in sorted(plants_dir.glob("*.yaml")):
        try:
            if not load_object_spec(p.stem).is_example:
                ids.append(p.stem)
        except Exception:
            continue
    return ids


def get_field_trip_audit(
    object_id: str, aggregate_id: str, *, database: AuditDatabase | None = None
) -> tuple[ObjectSpec, AuditResult]:
    """Выездной замер по паспорту с подтверждённой плотностью объекта из БД."""
    obj = load_object_spec(object_id)
    db = database if database is not None else AuditDatabase(default_database_path())
    obj = with_confirmed_density(obj, db)
    return obj, run_energy_audit(obj, aggregate_id)


def with_confirmed_density(obj: ObjectSpec, database: AuditDatabase) -> ObjectSpec:
    at = datetime.now(ZoneInfo("Europe/Moscow")).date()
    reading = database.plant_density_default(obj.id, at)
    if not reading:
        return obj
    obj = obj.model_copy(deep=True)
    for aggregate in obj.aggregates:
        if aggregate.regime is not None:
            aggregate.regime.rho = reading["density_kgm3"]
    return obj


def object_index(
    database: AuditDatabase,
) -> list[dict]:
    """Список объектов с метаданными для выбора/фильтра."""
    db = database
    out = []
    for record in db.plants(include_examples=True):
        if record["is_example"] and record["code"] != "demo-ppd":
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
            "has_telemetry": any(
                db.telemetry_dates(oid, aggregate["code"]) for aggregate in aggregates
            ),
        })
    return out


def get_verification() -> dict:
    """Двусторонняя сверка модель↔xlsx. Возвращает строки как dict."""
    res = run_verification(save_specs=False)
    from ppd_audit.verify.compare import row_to_dict

    return {
        "rows": [row_to_dict(r) for r in res["rows"]],
        "summary": res["summary"],
        "errors": res["errors"],
    }


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
    }
