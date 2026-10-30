"""Сериализация внешних CRM-выгрузок и простоев для обоих интерфейсов."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

import yaml

from ..ingest.crm_forecast import CrmForecastError, aggregate_names, discover_runs, read_daily
from ..ingest.crm_wells import (
    CrmWellsError,
    discover_runs as discover_well_runs,
    read_graph as read_wells_graph,
    read_report as read_wells_report,
)
from ..ingest.downtime import DowntimeError, normalize_well, read_downtime
from ..ingest.scada_txt import ScadaMapping
from ..report.wells_layout import spring_layout


def crm_runs(crm_dir: Path, object_id: str) -> list[dict]:
    """Прогоны CRM-прогноза для объекта: код, подпись, модель, события."""
    return [
        {
            "code": run.code,
            "title": run.title,
            "events": run.events,
            "object_id": run.object_id,
            "model": run.model,
        }
        for run in discover_runs(crm_dir / object_id)
    ]


def crm_daily_forecast(
    crm_dir: Path, scada_tags: Path, object_id: str, run_code: str
) -> dict | None:
    """Суточные объёмы прогноза по агрегатам и станции.

    Коды узлов модели (``PUMP_001``) переводятся в коды агрегатов БД
    (``НА-1``) по тому же ``config/scada_tags.yaml``, по которому грузится
    телеметрия, — иначе прогноз не с чем было бы сводить.
    """
    runs = {run.code: run for run in discover_runs(crm_dir / object_id)}
    run = runs.get(run_code)
    if run is None:
        return None
    try:
        mapping = ScadaMapping.from_yaml(scada_tags)
        daily = read_daily(run, aggregate_names(mapping.objects, run.object_id))
    except (CrmForecastError, OSError, yaml.YAMLError) as error:
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


def crm_well_runs(crm_dir: Path, object_id: str) -> list[dict]:
    """Прогоны CRM по нагнетательным скважинам для объекта."""
    return [
        {"code": run.code, "title": run.title, "mode": run.mode}
        for run in discover_well_runs(crm_dir / object_id)
    ]


def crm_wells_report(crm_dir: Path, object_id: str, run_code: str) -> dict | None:
    """Помесячная закачка по скважинам: прогноз, база и факт."""
    runs = {run.code: run for run in discover_well_runs(crm_dir / object_id)}
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
                "well_key": well_key(row.well),
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


def crm_wells_graph(
    crm_dir: Path, object_id: str, run_code: str, edge_limit: int = 60
) -> dict | None:
    """Граф взаимовлияния скважин: сильнейшие связи и центральности."""
    runs = {run.code: run for run in discover_well_runs(crm_dir / object_id)}
    run = runs.get(run_code)
    if run is None:
        return None
    try:
        graph = read_wells_graph(run)
        report = read_wells_report(run)
    except (CrmWellsError, OSError) as error:
        return {"error": str(error)}
    edges = graph.strongest(edge_limit)
    nodes = sorted(
        set(report.wells) | {node for edge in edges for node in (edge.source, edge.target)}
    )
    return {
        "positions": spring_layout(
            nodes, [(edge.source, edge.target, edge.strength) for edge in edges]
        ),
        "edges": [
            {"source": edge.source, "target": edge.target, "strength": edge.strength}
            for edge in edges
        ],
        "by_well": {
            well: [
                {"target": edge.target, "strength": edge.strength}
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


def well_downtime(downtime_dir: Path, object_id: str) -> list[dict]:
    """Причины простоев скважин объекта из промысловой сводки."""
    try:
        records = read_downtime(downtime_dir / f"{object_id}.xlsx")
    except DowntimeError:
        return []
    return [
        {
            "well": record.well,
            "well_key": well_key(record.well),
            "reason": record.reason,
            "since": record.since.isoformat(timespec="minutes") if record.since else None,
            "runtime_hours": record.runtime_hours,
        }
        for record in records
    ]


def well_key(name: str) -> str:
    """Ключ сопоставления скважины между сводкой простоев и выгрузкой CRM.

    В одном источнике скважина записана как «3592Д», в другом — «3592Д/2»:
    хвост после косой черты означает ствол, и по нему ряды расходятся.
    """
    return normalize_well(name)


def observed_station_totals(series: list[list[tuple[str, float]]]) -> dict[date, float]:
    """Суточный факт суммой по тем же агрегатам, что представлены в CRM."""
    totals: dict[date, float] = {}
    for points in series:
        for day, value in points:
            key = date.fromisoformat(day)
            totals[key] = totals.get(key, 0.0) + value
    return totals


def well_monthly_series(report: dict, well: str | None) -> list[dict]:
    """Помесячный ряд: сумма по объекту либо одна скважина."""
    if well is None:
        return report["totals"]
    return [
        {
            "month": row["month"],
            "base": row["base"] or 0.0,
            "forecast": row["forecast"] or 0.0,
            "fact": row["fact"],
        }
        for row in report["rows"]
        if row["well"] == well
    ]


def monthly_window(totals: list[dict]) -> tuple[datetime, datetime]:
    """Окно от начала первого месяца до начала месяца после последнего."""
    months = [date.fromisoformat(item["month"]) for item in totals]
    last = months[-1]
    end = date(last.year + last.month // 12, last.month % 12 + 1, 1)
    return datetime.combine(months[0], time.min), datetime.combine(end, time.min)


def downtime_in_window(totals: list[dict], downtime: list[dict]) -> list[dict]:
    """Сохранить только простои, начавшиеся в показанном помесячном окне."""
    first, end = monthly_window(totals)
    return [
        item
        for item in downtime
        if item["since"] and first <= datetime.fromisoformat(item["since"]) < end
    ]


def monthly_view(report: dict, downtime: list[dict], well: str | None = None) -> dict:
    """Подготовить один помесячный экран, включая окно и видимые начала простоев."""
    series = well_monthly_series(report, well)
    if not series:
        return {"series": [], "downtime_marks": [], "window": None, "last": None}
    selected_downtime = (
        downtime
        if well is None
        else [item for item in downtime if well_key(item["well"]) == well_key(well)]
    )
    return {
        "series": series,
        "downtime_marks": downtime_in_window(series, selected_downtime),
        "window": [moment.isoformat() for moment in monthly_window(series)],
        "last": series[-1],
    }
