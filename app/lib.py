"""Data-слой Streamlit-приложения: кешируемые обёртки над расчётным ядром.

Отделяет UI от ядра: страницы вызывают только функции отсюда.
"""

from __future__ import annotations

import math
import os
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
from ppd_audit.core.reservoir.forecast import (  # noqa: E402
    aggregate_daily_to_periods,
    forecast_injection,
)
from ppd_audit.db import AuditDatabase, default_database_path  # noqa: E402
from ppd_audit.db_seed import (  # noqa: E402
    DEFAULT_SCADA_DIRNAME,
    DEFAULT_TELEMETRY_DIRNAME,
    SCADA_TAGS_CONFIG,
    ScadaSeedResult,
    TelemetrySeedResult,
    bootstrap_database,
    seed_telemetry_from_excel,
    seed_telemetry_from_scada,
)
from ppd_audit.ingest.crm_forecast import (  # noqa: E402
    CRM_DIRNAME,
    CrmForecastError,
    aggregate_names,
    discover_runs,
    read_daily,
)
from ppd_audit.ingest.crm_wells import (  # noqa: E402
    CrmWellsError,
    discover_runs as discover_well_runs,
    read_graph as read_wells_graph,
    read_report as read_wells_report,
)
from ppd_audit.ingest.downtime import (  # noqa: E402
    DOWNTIME_DIRNAME,
    DowntimeError,
    normalize_well,
    read_downtime,
)
from ppd_audit.ingest.scada_txt import ScadaMapping  # noqa: E402
from ppd_audit.measures.economics import (  # noqa: E402
    DEFAULT_HORIZON_YEARS,
    InjectionProfile,
    build_annual_profile,
)
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
from ppd_audit.verify.runner import run_verification  # noqa: E402


WATER_ORDER = ["пресная", "агрессивная", "пластовая"]


TELEMETRY_DIR = _ROOT / "data" / DEFAULT_TELEMETRY_DIRNAME
SCADA_DIR = TELEMETRY_DIR / DEFAULT_SCADA_DIRNAME
SCADA_TAGS = _ROOT / "config" / SCADA_TAGS_CONFIG
CRM_DIR = _ROOT / "data" / CRM_DIRNAME
DOWNTIME_DIR = _ROOT / "data" / DOWNTIME_DIRNAME


@st.cache_resource(show_spinner="Первый запуск: читаем паспорта и выгрузки телеметрии…")
def _bootstrap():
    """Разовая подготовка БД. Возвращает путь, а не объект базы.

    Объект здесь кэшировать нельзя: ``st.cache_resource`` переживает
    обновление кода, и после деплоя в кэше остаётся экземпляр, собранный по
    прежней версии класса — новые методы у него отсутствуют, и приложение
    падает с AttributeError до перезапуска. Путь же переживает обновление
    безболезненно, а собрать ``AuditDatabase`` заново стоит один вызов
    конструктора: соединение открывается на каждую операцию отдельно.
    """
    path = default_database_path()
    db = bootstrap_database(path, _ROOT / "config" / "plants")
    scada = (
        seed_telemetry_from_scada(db, SCADA_DIR, SCADA_TAGS)
        if os.getenv("PPD_SKIP_SCADA_TELEMETRY") != "1"
        else ScadaSeedResult(SCADA_DIR, 0, 0, reason="импорт выгрузок отключён")
    )
    seed = seed_telemetry_from_excel(
        db, TELEMETRY_DIR, include_examples=os.getenv("PPD_SKIP_EXAMPLE_TELEMETRY") != "1"
    )
    return path, seed, scada


def database() -> AuditDatabase:
    return AuditDatabase(_bootstrap()[0])


def telemetry_seed_status() -> TelemetrySeedResult:
    return _bootstrap()[1]


def scada_seed_status() -> ScadaSeedResult:
    return _bootstrap()[2]


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
    """Ключ выбранного момента: один для вкладок «Обзор» и «Режимный расчёт»."""
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


USABLE_DAY_STATUSES = ("ready", "snapshot", "unfit")


@st.cache_data(show_spinner=False)
def last_usable_day(object_id: str, aggregate_id: str, scan_limit: int = 60):
    """Последние сутки, за которые вообще строится режим.

    Дашборд открывается на них. Просто «последняя дата с суточными итогами»
    не годится: на КНС-ОПУ подача агрегата получается распределением
    станционного расхода, и почти простоявшие сутки дают крохотный, но
    ненулевой объём — открывать дашборд на них бессмысленно. Идём от конца
    назад по датам, пока не найдём сутки со статусом не «insufficient».

    Просмотр ограничен ``scan_limit`` сутками: у агрегата, который не считается
    в принципе (нет паспортных КПД, стоит месяцами), полный перебор 400 дней
    занял бы секунды на каждом открытии. Не нашли — возвращаем None, и вызов
    откатывается на прежнее умолчание.
    """
    dates = telemetry_dates(object_id, aggregate_id)
    if not dates:
        return None
    for day in reversed(dates[-scan_limit:]):
        if telemetry_day_status(object_id, aggregate_id, day) in USABLE_DAY_STATUSES:
            return day
    return None


def last_complete_day(object_id: str, aggregate_id: str):
    """Последние сутки с суточными итогами; None — таких нет."""
    return database().last_day_with_daily_totals(object_id, aggregate_id)


def telemetry_date_statuses(
    object_id: str, aggregate_id: str, dates: list[date]
) -> dict[date, str]:
    return _telemetry_date_statuses(database(), object_id, aggregate_id, dates)


def telemetry_day_status(object_id: str, aggregate_id: str, day: date) -> str:
    return _telemetry_day_status(database(), object_id, aggregate_id, day)


def telemetry_for_day(object_id: str, aggregate_id: str, day: date) -> list[dict]:
    """События агрегата за сутки и актуальное на начало суток давление."""
    start = datetime.combine(day, datetime.min.time())
    return _telemetry_for_window(object_id, aggregate_id, start, start + timedelta(days=1))


def telemetry_for_period(
    object_id: str, aggregate_id: str, start_day: date, end_day: date
) -> list[dict]:
    """Сырые точки агрегата и станции за выбранные дни включительно."""
    start = datetime.combine(start_day, datetime.min.time())
    end = datetime.combine(end_day + timedelta(days=1), datetime.min.time())
    return _telemetry_for_window(object_id, aggregate_id, start, end)


def daily_injection_series(
    object_id: str, aggregate_id: str, start_day: date, end_day: date
) -> list[tuple[str, float]]:
    """Суточные объёмы закачки (метрика q_day) по датам, от старых к новым.

    Приоритет — значение самого агрегата; станционное берётся только там, где
    своего нет. Общая точка входа для вкладки прогноза и для экономики
    мероприятий, чтобы обе считали ряд одинаково.
    """
    rows = telemetry_for_period(object_id, aggregate_id, start_day, end_day)
    by_date: dict[str, float] = {}
    for row in rows:
        if row["metric"] != "q_day":
            continue
        day_key = row["timestamp"][:10]
        if row["is_station"] and day_key in by_date:
            continue
        if (not row["is_station"]) or day_key not in by_date:
            by_date[day_key] = row["value"]
    return sorted(by_date.items())


@st.cache_data(show_spinner=False)
def crm_runs(object_id: str) -> list[dict]:
    """Прогоны CRM-прогноза для объекта: код, подпись, модель, события."""
    return [
        {
            "code": run.code,
            "title": run.title,
            "events": run.events,
            "object_id": run.object_id,
            "model": run.model,
        }
        for run in discover_runs(CRM_DIR / object_id)
    ]


@st.cache_data(show_spinner="Читаем выгрузку CRM-прогноза…")
def crm_daily_forecast(object_id: str, run_code: str) -> dict | None:
    """Суточные объёмы прогноза по агрегатам и станции.

    Коды узлов модели (``PUMP_001``) переводятся в коды агрегатов БД
    (``НА-1``) по тому же ``config/scada_tags.yaml``, по которому грузится
    телеметрия, — иначе прогноз не с чем было бы сводить.
    """
    runs = {run.code: run for run in discover_runs(CRM_DIR / object_id)}
    run = runs.get(run_code)
    if run is None:
        return None
    mapping = ScadaMapping.from_yaml(SCADA_TAGS)
    try:
        daily = read_daily(run, aggregate_names(mapping.objects, run.object_id))
    except CrmForecastError as error:
        return {"error": str(error)}
    return {
        "interval_hours": daily.interval_hours,
        "by_unit": {
            unit: sorted((day.isoformat(), value) for day, value in series.items())
            for unit, series in daily.by_unit.items()
        },
        "total": sorted((day.isoformat(), value) for day, value in daily.total.items()),
        "partial_days": [day.isoformat() for day in daily.partial_days],
        "model": run.model,
        "events": run.events,
    }


@st.cache_data(show_spinner=False)
def crm_well_runs(object_id: str) -> list[dict]:
    """Прогоны CRM по нагнетательным скважинам для объекта."""
    return [
        {"code": run.code, "title": run.title, "mode": run.mode}
        for run in discover_well_runs(CRM_DIR / object_id)
    ]


@st.cache_data(show_spinner="Читаем прогноз по скважинам…")
def crm_wells_report(object_id: str, run_code: str) -> dict | None:
    """Помесячная закачка по скважинам: прогноз, база и факт."""
    runs = {run.code: run for run in discover_well_runs(CRM_DIR / object_id)}
    run = runs.get(run_code)
    if run is None:
        return None
    try:
        report = read_wells_report(run)
    except CrmWellsError as error:
        return {"error": str(error)}
    return {
        "months": [month.isoformat() for month in report.months],
        "wells": list(report.wells),
        "has_fact": report.has_fact,
        "totals": [
            {
                "month": item.month.isoformat(),
                "base": item.base,
                "forecast": item.forecast,
                "fact": item.fact,
            }
            for item in report.totals()
        ],
        "rows": [
            {
                "month": row.month.isoformat(),
                "well": row.well,
                "base": row.base,
                "forecast": row.forecast,
                "fact": row.fact,
                "deviation": row.deviation_percent,
                "share": row.share,
                "r_ust": row.r_ust,
                "r_ust_fact": row.r_ust_fact,
            }
            for row in report.rows
        ],
    }


@st.cache_data(show_spinner=False)
def crm_wells_graph(object_id: str, run_code: str, edge_limit: int = 60) -> dict | None:
    """Граф взаимовлияния скважин: сильнейшие связи и центральности."""
    runs = {run.code: run for run in discover_well_runs(CRM_DIR / object_id)}
    run = runs.get(run_code)
    if run is None:
        return None
    graph = read_wells_graph(run)
    return {
        "edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "strength": edge.strength,
                "signed": edge.signed,
            }
            for edge in graph.strongest(edge_limit)
        ],
        "by_well": {
            well: [
                {"target": edge.target, "strength": edge.strength, "signed": edge.signed}
                for edge in graph.neighbours(well)
            ]
            for well in {edge.source for edge in graph.edges}
        },
        "centrality": [
            {
                "well": item.well,
                "strength_sum": item.strength_sum,
                "degree": item.degree,
                "betweenness": item.betweenness,
                "top_neighbor": item.top_neighbor,
                "top_neighbor_strength": item.top_neighbor_strength,
            }
            for item in graph.centrality
        ],
    }


def well_key(name: str) -> str:
    """Ключ сопоставления скважины между сводкой простоев и выгрузкой CRM.

    В одном источнике скважина записана как «3592Д», в другом — «3592Д/2»:
    хвост после косой черты означает ствол, и по нему ряды расходятся.
    """
    return normalize_well(name)


@st.cache_data(show_spinner=False)
def well_downtime(object_id: str) -> list[dict]:
    """Причины простоев скважин объекта из промысловой сводки."""
    try:
        records = read_downtime(DOWNTIME_DIR / f"{object_id}.xlsx")
    except DowntimeError:
        return []
    return [
        {
            "well": record.well,
            "reason": record.reason,
            "since": record.since.isoformat() if record.since else None,
            "runtime_hours": record.runtime_hours,
        }
        for record in records
    ]


def injection_profile(
    object_id: str,
    aggregate_id: str,
    base_annual_m3: float,
    *,
    horizon_years: int = DEFAULT_HORIZON_YEARS,
    period_days: int = 30,
) -> InjectionProfile | None:
    """Прогнозный профиль закачки по годам горизонта.

    Возвращает ``None``, если телеметрии не хватает на трендовую
    экстраполяцию (нужно ≥3 полных периода) — вызывающая сторона должна
    честно сказать об этом пользователю, а не подсовывать выдуманный профиль.
    """
    dates = telemetry_dates(object_id, aggregate_id)
    if len(dates) < 3:
        return None
    series = daily_injection_series(object_id, aggregate_id, dates[0], dates[-1])
    daily = [value for _, value in series]
    history = aggregate_daily_to_periods(daily, days_per_period=period_days)
    if len(history) < 3:
        return None

    horizon_periods = math.ceil(horizon_years * 365 / period_days)
    forecast = forecast_injection(history, horizon=horizon_periods)
    return build_annual_profile(
        [point.value for point in forecast.points],
        period_days=period_days,
        horizon_years=horizon_years,
        base_annual_m3=base_annual_m3,
        lower_values=[point.lower for point in forecast.points],
        upper_values=[point.upper for point in forecast.points],
        method=forecast.method,
        note=forecast.note,
    )


def _telemetry_for_window(
    object_id: str, aggregate_id: str, start: datetime, end: datetime
) -> list[dict]:
    database_ = database()
    rows = database_.measurements_in_window(
        object_id, aggregate_id, start, end, include_station=True
    )
    state_rows = database_.state_measurements_in_window(
        object_id, aggregate_id, start, end, include_end=True
    )
    return [
        row for row in rows if row["metric"] not in {"p_in", "p_out", "p_bg", "power"}
    ] + state_rows


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
