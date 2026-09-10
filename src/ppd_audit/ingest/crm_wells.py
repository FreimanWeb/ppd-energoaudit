"""Чтение выгрузок CRM по нагнетательным скважинам.

Внешний пайплайн считает помесячную закачку по каждой нагнетательной
скважине КНС и, в ретроспективном режиме, кладёт рядом факт. Отдельно он
сохраняет граф взаимовлияния скважин — ядро CRM: какая скважина на какую
влияет и насколько сильно.

Раскладка в репозитории::

    data/crm/<объект>/<прогон>/predicted_injector_report_like.csv
    data/crm/<объект>/<прогон>/loaded_model_injector_interdependence_edges.csv
    data/crm/<объект>/<прогон>/loaded_model_injector_dependency_centrality.csv
    data/crm/<объект>/<прогон>/run.json           подпись прогона, необязательно

Имена файлов — те же, что выдаёт пайплайн: папку прогона можно положить как
есть. Номер КНС из самой таблицы не берётся: пайплайн проставляет туда 97
для любого объекта, поэтому объект определяется папкой.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterator


REPORT_FILE = "predicted_injector_report_like.csv"
EDGES_FILE = "loaded_model_injector_interdependence_edges.csv"
CENTRALITY_FILE = "loaded_model_injector_dependency_centrality.csv"
RUN_FILE = "run.json"

MONTH_COLUMN = "Период"
WELL_COLUMN = "Нагн. скваж."
COLUMNS = {
    "base": "Закачка м3/мес базовый прогноз",
    "forecast": "Закачка м3/мес прогноз",
    "fact": "Закачка м3/мес факт",
    "share": "Доля прогноз",
    "r_ust": "Руст прогноз",
    "r_ust_fact": "Руст факт",
}


class CrmWellsError(ValueError):
    """Выгрузка по скважинам не читается."""


@dataclass(frozen=True)
class WellRun:
    """Прогон прогноза по скважинам: папка и подпись."""

    path: Path
    code: str
    title: str
    mode: str | None = None

    @property
    def report(self) -> Path:
        candidate = self.path / REPORT_FILE
        if not candidate.exists():
            raise CrmWellsError(f"в {self.path} нет файла {REPORT_FILE}")
        return candidate


@dataclass(frozen=True)
class WellRow:
    """Строка отчёта: скважина за месяц."""

    month: date
    well: str
    base: float | None = None
    forecast: float | None = None
    fact: float | None = None
    share: float | None = None
    r_ust: float | None = None
    r_ust_fact: float | None = None

    @property
    def deviation_percent(self) -> float | None:
        """Отклонение прогноза от факта, %; None — факта нет или он нулевой."""
        if self.fact is None or self.forecast is None or abs(self.fact) < 1e-9:
            return None
        return (self.forecast - self.fact) / self.fact * 100.0


@dataclass(frozen=True)
class MonthTotals:
    """Суммарная закачка КНС за месяц по трём рядам."""

    month: date
    base: float = 0.0
    forecast: float = 0.0
    fact: float | None = None


@dataclass(frozen=True)
class Edge:
    """Связь двух скважин: сила и знак взаимовлияния."""

    source: str
    target: str
    strength: float
    signed: float


@dataclass(frozen=True)
class Centrality:
    """Место скважины в графе: связность и сильнейший сосед."""

    well: str
    strength_sum: float = 0.0
    degree: float = 0.0
    betweenness: float = 0.0
    top_neighbor: str = ""
    top_neighbor_strength: float = 0.0


@dataclass(frozen=True)
class WellsReport:
    """Разобранный отчёт прогона."""

    run: WellRun
    rows: tuple[WellRow, ...] = ()
    months: tuple[date, ...] = ()
    wells: tuple[str, ...] = ()
    has_fact: bool = False

    def for_month(self, month: date) -> list[WellRow]:
        return [row for row in self.rows if row.month == month]

    def totals(self) -> list[MonthTotals]:
        by_month: dict[date, list[WellRow]] = {}
        for row in self.rows:
            by_month.setdefault(row.month, []).append(row)
        totals = []
        for month in sorted(by_month):
            group = by_month[month]
            facts = [row.fact for row in group if row.fact is not None]
            totals.append(
                MonthTotals(
                    month=month,
                    base=sum(row.base or 0.0 for row in group),
                    forecast=sum(row.forecast or 0.0 for row in group),
                    fact=sum(facts) if facts else None,
                )
            )
        return totals


@dataclass(frozen=True)
class WellsGraph:
    """Граф взаимовлияния скважин."""

    edges: tuple[Edge, ...] = ()
    centrality: tuple[Centrality, ...] = field(default=())

    def neighbours(self, well: str, limit: int = 10) -> list[Edge]:
        """Сильнейшие связи скважины, от сильных к слабым."""
        own = [edge for edge in self.edges if edge.source == well]
        return sorted(own, key=lambda edge: -edge.strength)[:limit]

    def strongest(self, limit: int = 60) -> list[Edge]:
        """Самые сильные связи графа без дублей «туда-обратно»."""
        seen: set[tuple[str, str]] = set()
        out = []
        for edge in sorted(self.edges, key=lambda e: -e.strength):
            key = tuple(sorted((edge.source, edge.target)))
            if key in seen:
                continue
            seen.add(key)
            out.append(edge)
            if len(out) >= limit:
                break
        return out


def parse_month(text: str) -> date:
    """«04.2026» или «2026-04» → первое число месяца."""
    value = (text or "").strip()
    for separator, order in ((".", "reverse"), ("-", "direct")):
        if separator in value:
            parts = value.split(separator)
            if len(parts) != 2:
                continue
            first, second = parts
            year, month = (second, first) if order == "reverse" else (first, second)
            try:
                return date(int(year), int(month), 1)
            except ValueError:
                continue
    raise CrmWellsError(f"не разобрать период «{text}»")


def parse_value(text: str | None) -> float | None:
    value = (text or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return None if number != number else number  # NaN


def _read_csv(path: Path) -> Iterator[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def read_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def discover_runs(object_dir: Path) -> list[WellRun]:
    """Прогоны с отчётом по скважинам внутри data/crm/<объект>."""
    if not object_dir.is_dir():
        return []
    runs = []
    for directory in sorted(p for p in object_dir.iterdir() if p.is_dir()):
        if not (directory / REPORT_FILE).exists():
            continue
        meta = read_metadata(directory / RUN_FILE)
        runs.append(
            WellRun(
                path=directory,
                code=directory.name,
                title=str(meta.get("title") or directory.name),
                mode=meta.get("mode"),
            )
        )
    return runs


def read_report(run: WellRun) -> WellsReport:
    """Разобрать помесячный отчёт по скважинам."""
    rows: list[WellRow] = []
    for record in _read_csv(run.report):
        month_text = record.get(MONTH_COLUMN)
        well = (record.get(WELL_COLUMN) or "").strip()
        if not month_text or not well:
            continue
        values = {key: parse_value(record.get(column)) for key, column in COLUMNS.items()}
        rows.append(WellRow(month=parse_month(month_text), well=well, **values))

    if not rows:
        raise CrmWellsError(f"в {run.report.name} нет ни одной строки")

    return WellsReport(
        run=run,
        rows=tuple(rows),
        months=tuple(sorted({row.month for row in rows})),
        wells=tuple(sorted({row.well for row in rows})),
        has_fact=any(row.fact is not None for row in rows),
    )


def read_graph(run: WellRun) -> WellsGraph:
    """Связи и центральности; отсутствующие файлы дают пустой граф."""
    edges = []
    edges_path = run.path / EDGES_FILE
    if edges_path.exists():
        for record in _read_csv(edges_path):
            source = (record.get("source") or "").strip()
            target = (record.get("target") or "").strip()
            if not source or not target:
                continue
            edges.append(
                Edge(
                    source=source,
                    target=target,
                    strength=parse_value(record.get("combined_strength")) or 0.0,
                    signed=parse_value(record.get("combined_signed")) or 0.0,
                )
            )

    centrality = []
    centrality_path = run.path / CENTRALITY_FILE
    if centrality_path.exists():
        for record in _read_csv(centrality_path):
            well = (record.get("injector") or "").strip()
            if not well:
                continue
            centrality.append(
                Centrality(
                    well=well,
                    strength_sum=parse_value(record.get("strength_sum")) or 0.0,
                    degree=parse_value(record.get("degree_centrality")) or 0.0,
                    betweenness=parse_value(record.get("betweenness_centrality")) or 0.0,
                    top_neighbor=(record.get("top_neighbor") or "").strip(),
                    top_neighbor_strength=parse_value(record.get("top_neighbor_strength")) or 0.0,
                )
            )

    return WellsGraph(edges=tuple(edges), centrality=tuple(centrality))
