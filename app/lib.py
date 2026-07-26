"""Data-слой Streamlit-приложения: кешируемые обёртки над расчётным ядром.

Отделяет UI от ядра: страницы вызывают только функции отсюда.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st


# Пакет лежит в src/ — добавляем в путь при запуске `streamlit run app/main.py`
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from ppd_audit.config import load_constraints  # noqa: E402
from ppd_audit.core.audit import AuditResult  # noqa: E402
from ppd_audit.db import default_database_path  # noqa: E402
from ppd_audit.db_seed import bootstrap_database  # noqa: E402
from ppd_audit.services.audit import run_energy_audit  # noqa: E402
from ppd_audit.services.result_scope import ResultScope, result_scope as _result_scope  # noqa: E402
from ppd_audit.services.telemetry_audit import (  # noqa: E402
    excluded_snapshots_by_manifold_pressure as _excluded_snapshots_by_manifold_pressure,
    object_from_database,
    run_snapshot_audit,
    run_telemetry_audit,
    telemetry_date_statuses as _telemetry_date_statuses,
    telemetry_day_status as _telemetry_day_status,
    telemetry_snapshots as _telemetry_snapshots,
)
from ppd_audit.spec import ObjectSpec, load_object_spec  # noqa: E402
from ppd_audit.verify.reconcile import run_reconciliation  # noqa: E402
from ppd_audit.verify.runner import run_verification  # noqa: E402


WATER_ORDER = ["пресная", "агрессивная", "пластовая"]


def database():
    return bootstrap_database(default_database_path(), _ROOT / "config" / "plants")


def list_object_ids() -> list[str]:
    """Все объекты из config/plants/*.yaml, для которых грузится спец."""
    ids = []
    for p in sorted((_ROOT / "config" / "plants").glob("*.yaml")):
        try:
            if not load_object_spec(p.stem).is_example:
                ids.append(p.stem)
        except Exception:
            continue
    return ids


def get_object(object_id: str, at: datetime, aggregate_id: str | None = None) -> ObjectSpec:
    return object_from_database(database(), object_id, at, aggregate_code=aggregate_id)


def get_field_trip_audit(object_id: str, aggregate_id: str) -> tuple[ObjectSpec, AuditResult]:
    """Рассчитать выездной замер исключительно по YAML-паспорту объекта."""
    obj = load_object_spec(object_id)
    return obj, run_energy_audit(obj, aggregate_id)


def field_trip_scope(regime) -> ResultScope:
    """Статус годовой оценки для выездного замера из YAML."""
    return _result_scope(regime, regime.t_year)


def object_index() -> list[dict]:
    """Список объектов с метаданными для выбора/фильтра."""
    db = database()
    out = []
    for record in db.plants():
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


def open_clarifications(object_id: str, aggregate_id: str) -> list[dict[str, str]]:
    """Временные паспортные значения выбранного агрегата."""
    return database().clarifications(object_id, aggregate_id)


def get_audit(
    object_id: str,
    aggregate_id: str,
    start: datetime,
    end: datetime,
    *,
    require_daily_pressure_coverage: bool = True,
) -> AuditResult:
    return run_telemetry_audit(
        database(),
        object_id,
        aggregate_id,
        start,
        end,
        require_daily_pressure_coverage=require_daily_pressure_coverage,
    )


def telemetry_snapshots(
    object_id: str, aggregate_id: str, start: datetime, end: datetime,
):
    return _telemetry_snapshots(database(), object_id, aggregate_id, start, end)


def excluded_snapshots_by_manifold_pressure(
    object_id: str, aggregate_id: str, start: datetime, end: datetime
) -> int:
    return _excluded_snapshots_by_manifold_pressure(
        database(), object_id, aggregate_id, start, end
    )


def snapshot_selection_key(object_id: str, aggregate_id: str, day: date) -> str:
    """Ключ выбранного снимка: один для вкладок «Анализ» и «Режимный снимок»."""
    return f"snapshot-{object_id}-{aggregate_id}-{day.isoformat()}"


def get_snapshot_audit(
    object_id: str,
    aggregate_id: str,
    start: datetime,
    end: datetime,
    timestamp: datetime,
):
    return run_snapshot_audit(database(), object_id, aggregate_id, start, end, timestamp)


def telemetry_dates(object_id: str, aggregate_id: str) -> list[date]:
    return database().telemetry_dates(object_id, aggregate_id)


def telemetry_date_statuses(
    object_id: str, aggregate_id: str, dates: list[date]
) -> dict[date, str]:
    return _telemetry_date_statuses(database(), object_id, aggregate_id, dates)


def telemetry_day_status(object_id: str, aggregate_id: str, day: date) -> str:
    return _telemetry_day_status(database(), object_id, aggregate_id, day)


def telemetry_for_day(object_id: str, aggregate_id: str, day: date) -> list[dict]:
    """Сырые точки агрегата и станции за сутки — для графиков без эвристик."""
    start = datetime.combine(day, datetime.min.time())
    return database().measurements_in_window(
        object_id,
        aggregate_id,
        start,
        start + timedelta(days=1),
        include_station=True,
    )


def telemetry_for_period(
    object_id: str, aggregate_id: str, start_day: date, end_day: date
) -> list[dict]:
    """Сырые точки агрегата и станции за выбранные дни включительно."""
    start = datetime.combine(start_day, datetime.min.time())
    end = datetime.combine(end_day + timedelta(days=1), datetime.min.time())
    return database().measurements_in_window(
        object_id, aggregate_id, start, end, include_station=True
    )


def result_scope_for(
    object_id: str,
    aggregate_id: str,
    end: datetime,
    regime,
    *,
    daily_pressure_coverage_is_complete: bool = True,
) -> ResultScope:
    """Статус суточного KPI и годовой оценки для отображения в UI."""
    return _result_scope(
        regime,
        database().annual_runtime(object_id, aggregate_id, end),
        daily_pressure_coverage_is_complete=daily_pressure_coverage_is_complete,
    )


@st.cache_data(show_spinner=True)
def get_verification() -> dict:
    """Двусторонняя сверка модель↔xlsx. Возвращает строки как dict."""
    res = run_verification(save_specs=False)
    from ppd_audit.verify.compare import row_to_dict

    return {
        "rows": [row_to_dict(r) for r in res["rows"]],
        "summary": res["summary"],
        "errors": res["errors"],
    }


@st.cache_resource(show_spinner=True)
def _reconciliation():
    """Сырая трёхсторонняя сверка (один прогон на сессию; .doc уже сконвертированы)."""
    return run_reconciliation()


@st.cache_data(show_spinner=True)
def get_reconciliation() -> dict:
    """Трёхсторонняя сверка модель↔xlsx↔отчёт (для экрана «Модель vs Отчёт»)."""
    from dataclasses import asdict

    res = _reconciliation()
    return {
        "rows": [asdict(r) for r in res["rows"]],
        "summary": res["summary"],
        "errors": res["errors"],
    }


@st.cache_data(show_spinner=False)
def get_report_facts(object_id: str) -> dict:
    """Цитаты и ТЭО из текстового отчёта объекта (для карточки объекта)."""
    res = _reconciliation()
    rep = res["reports"].get(object_id)
    if rep is None:
        return {}
    return {
        "source": rep.source_original or rep.source,
        "report_date": rep.report_date,
        "template": rep.template,
        "quotes": rep.quotes,
        "recommendations": rep.recommendations,
        "teo": rep.teo,
        "aggregates": {
            a.id: {
                "pump_model": a.pump_model,
                "claims": [
                    {
                        "metric": c.metric,
                        "min": c.value_min,
                        "max": c.value_max,
                        "unit": c.unit,
                        "text": c.text,
                    }
                    for c in a.claims
                ],
            }
            for a in rep.aggregates
        },
    }


@st.cache_data(show_spinner=False)
def tariff() -> float:
    return load_constraints().economics.get("tariff_rub_kwh", 4.68)


@st.cache_data(show_spinner=False)
def get_topology(object_id: str) -> dict | None:
    """As-built технологическая схема объекта (config/topology/<id>.yaml), если задана.

    Отдельный конфиг (узлы/трубопроводы) — не часть core-спеки, поэтому добавление
    топологии не влияет на расчётное ядро и его тесты.
    """
    import yaml

    p = _ROOT / "config" / "topology" / f"{object_id}.yaml"
    if not p.exists():
        return None
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def constraints():
    return load_constraints()
