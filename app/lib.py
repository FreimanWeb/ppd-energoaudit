"""Data-слой Streamlit-приложения: кешируемые обёртки над расчётным ядром.

Отделяет UI от ядра: страницы вызывают только функции отсюда.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import streamlit as st


# Пакет лежит в src/ — добавляем в путь при запуске `streamlit run app/main.py`
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from ppd_audit.config import load_constraints  # noqa: E402
from ppd_audit.core.audit import AuditResult  # noqa: E402
from ppd_audit.db import AuditDatabase  # noqa: E402
from ppd_audit.db_seed import (  # noqa: E402
    DEFAULT_SCADA_DIRNAME,
    DEFAULT_TELEMETRY_DIRNAME,
    ScadaSeedResult,
    TelemetrySeedResult,
)
from ppd_audit.measures.economics import (  # noqa: E402
    DEFAULT_HORIZON_YEARS,
    InjectionProfile,
)
from ppd_audit.services import catalog, crm_view, forecast_data, telemetry_view  # noqa: E402
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
from ppd_audit.spec import ObjectSpec  # noqa: E402


WATER_ORDER = ["пресная", "агрессивная", "пластовая"]


TELEMETRY_DIR = _ROOT / "data" / DEFAULT_TELEMETRY_DIRNAME
SCADA_DIR = TELEMETRY_DIR / DEFAULT_SCADA_DIRNAME
SCADA_TAGS = catalog.source_paths(_ROOT)["scada_tags"]
CRM_DIR = catalog.source_paths(_ROOT)["crm"]
DOWNTIME_DIR = catalog.source_paths(_ROOT)["downtime"]


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
    return catalog.bootstrap_app_data(_ROOT, TELEMETRY_DIR, SCADA_DIR, SCADA_TAGS)


def database() -> AuditDatabase:
    return AuditDatabase(_bootstrap()[0])


def telemetry_seed_status() -> TelemetrySeedResult:
    return _bootstrap()[1]


def scada_seed_status() -> ScadaSeedResult:
    return _bootstrap()[2]


def list_object_ids() -> list[str]:
    """Все объекты из config/plants/*.yaml, для которых грузится спец."""
    return catalog.list_object_ids(_ROOT / "config" / "plants")


def get_object(object_id: str, at: datetime, aggregate_id: str | None = None) -> ObjectSpec:
    return object_from_database(database(), object_id, at, aggregate_code=aggregate_id)


def get_field_trip_audit(object_id: str, aggregate_id: str) -> tuple[ObjectSpec, AuditResult]:
    """Рассчитать выездной замер исключительно по YAML-паспорту объекта."""
    return catalog.get_field_trip_audit(object_id, aggregate_id)


def field_trip_scope(regime) -> ResultScope:
    """Статус годовой оценки для выездного замера из YAML."""
    return _result_scope(regime, regime.t_year)


def object_index() -> list[dict]:
    """Список объектов с метаданными для выбора/фильтра."""
    return catalog.object_index(database())


def open_clarifications(object_id: str, aggregate_id: str) -> list[dict[str, str]]:
    """Временные паспортные значения выбранного агрегата."""
    return catalog.open_clarifications(database(), object_id, aggregate_id)


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
    object_id: str,
    aggregate_id: str,
    start: datetime,
    end: datetime,
):
    return _telemetry_snapshots(database(), object_id, aggregate_id, start, end)


def excluded_snapshots_by_manifold_pressure(
    object_id: str, aggregate_id: str, start: datetime, end: datetime
) -> int:
    return _excluded_snapshots_by_manifold_pressure(database(), object_id, aggregate_id, start, end)


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
    return telemetry_view.last_usable_day(database(), object_id, aggregate_id, scan_limit)


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
    return telemetry_view.telemetry_for_day(database(), object_id, aggregate_id, day)


def telemetry_for_period(
    object_id: str, aggregate_id: str, start_day: date, end_day: date
) -> list[dict]:
    """Сырые точки агрегата и станции за выбранные дни включительно."""
    return telemetry_view.telemetry_for_period(
        database(), object_id, aggregate_id, start_day, end_day
    )


def daily_injection_series(
    object_id: str, aggregate_id: str, start_day: date, end_day: date
) -> list[tuple[str, float]]:
    """Суточные объёмы закачки (метрика q_day) по датам, от старых к новым.

    Приоритет — значение самого агрегата; станционное берётся только там, где
    своего нет. Общая точка входа для вкладки прогноза и для экономики
    мероприятий, чтобы обе считали ряд одинаково.
    """
    return telemetry_view.daily_injection_series(
        database(), object_id, aggregate_id, start_day, end_day
    )


@st.cache_data(show_spinner=False)
def crm_runs(object_id: str) -> list[dict]:
    """Прогоны CRM-прогноза для объекта: код, подпись, модель, события."""
    return crm_view.crm_runs(CRM_DIR, object_id)


@st.cache_data(show_spinner="Читаем выгрузку CRM-прогноза…")
def crm_daily_forecast(object_id: str, run_code: str) -> dict | None:
    """Суточные объёмы прогноза по агрегатам и станции.

    Коды узлов модели (``PUMP_001``) переводятся в коды агрегатов БД
    (``НА-1``) по тому же ``config/scada_tags.yaml``, по которому грузится
    телеметрия, — иначе прогноз не с чем было бы сводить.
    """
    return crm_view.crm_daily_forecast(CRM_DIR, SCADA_TAGS, object_id, run_code)


@st.cache_data(show_spinner=False)
def crm_well_runs(object_id: str) -> list[dict]:
    """Прогоны CRM по нагнетательным скважинам для объекта."""
    return crm_view.crm_well_runs(CRM_DIR, object_id)


@st.cache_data(show_spinner="Читаем прогноз по скважинам…")
def crm_wells_report(object_id: str, run_code: str) -> dict | None:
    """Помесячная закачка по скважинам: прогноз, база и факт."""
    return crm_view.crm_wells_report(CRM_DIR, object_id, run_code)


@st.cache_data(show_spinner=False)
def crm_wells_graph(object_id: str, run_code: str, edge_limit: int = 60) -> dict | None:
    """Граф взаимовлияния скважин: сильнейшие связи и центральности."""
    return crm_view.crm_wells_graph(CRM_DIR, object_id, run_code, edge_limit)


def well_key(name: str) -> str:
    """Ключ сопоставления скважины между сводкой простоев и выгрузкой CRM.

    В одном источнике скважина записана как «3592Д», в другом — «3592Д/2»:
    хвост после косой черты означает ствол, и по нему ряды расходятся.
    """
    return crm_view.well_key(name)


@st.cache_data(show_spinner=False)
def well_downtime(object_id: str) -> list[dict]:
    """Причины простоев скважин объекта из промысловой сводки."""
    return crm_view.well_downtime(DOWNTIME_DIR, object_id)


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
    return forecast_data.injection_profile(
        database(),
        object_id,
        aggregate_id,
        base_annual_m3,
        horizon_years=horizon_years,
        period_days=period_days,
    )


def _telemetry_for_window(
    object_id: str, aggregate_id: str, start: datetime, end: datetime
) -> list[dict]:
    return telemetry_view.telemetry_for_window(database(), object_id, aggregate_id, start, end)


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
    return catalog.get_verification()


def tariff(at: date | None = None) -> float:
    try:
        selection = catalog.tariff(at, database=database())
    except ValueError as exc:
        st.warning(str(exc))
        st.stop()
    if selection["warning"]:
        st.warning(selection["warning"])
    return selection["rub_per_kwh"]


@st.cache_data(show_spinner=False)
def get_topology(object_id: str) -> dict | None:
    """As-built технологическая схема объекта (config/topology/<id>.yaml), если задана.

    Отдельный конфиг (узлы/трубопроводы) — не часть core-спеки, поэтому добавление
    топологии не влияет на расчётное ядро и его тесты.
    """
    return catalog.get_topology(_ROOT / "config" / "topology", object_id)


def constraints():
    return load_constraints()


def forecast_series(
    object_id: str,
    aggregate_id: str,
    start_day: date,
    end_day: date,
    *,
    period_days: int = 30,
    horizon: int = 36,
) -> dict:
    """Общие с API периоды истории и статистический прогноз."""
    return forecast_data.forecast_series(
        database(),
        object_id,
        aggregate_id,
        start_day,
        end_day,
        period_days=period_days,
        horizon=horizon,
    )
