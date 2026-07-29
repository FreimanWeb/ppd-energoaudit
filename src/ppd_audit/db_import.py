"""Однократная загрузка предоставленной тестовой телеметрии в SQLite."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .db import AuditDatabase, TelemetryMeasurement
from .ingest.excel_telemetry import build_excel_telemetry


@dataclass(frozen=True)
class ImportStats:
    stored: int
    skipped: int


def import_test_telemetry(database: AuditDatabase, root: Path) -> ImportStats:
    """Загрузить нормализованные JSON тестовой выборки с provenance каждой строки."""
    measurements: list[TelemetryMeasurement] = []
    skipped = 0
    for path in root.rglob("*.json"):
        target = _target(path.name)
        if target is None:
            continue
        (
            plant_code,
            aggregate_code,
            technical_place_code,
            pressure_multiplier,
            pressure_metric,
        ) = target
        if technical_place_code != "main":
            database.upsert_technical_place(plant_code, technical_place_code, "КНС-97 ЕН")
        if aggregate_code:
            database.upsert_aggregate(
                plant_code,
                aggregate_code,
                "работа",
                technical_place_code=technical_place_code,
            )
        draft = json.loads(path.read_text(encoding="utf-8"))
        for record in draft.get("telemetry", []):
            measurement = _measurement(
                record,
                plant_code,
                aggregate_code or _aggregate_from_tag(record.get("tag", ""), plant_code),
                technical_place_code,
                pressure_multiplier,
                pressure_metric,
                source_kind="json_draft",
                source_file=str(path.relative_to(root)),
            )
            if measurement is None:
                skipped += 1
            else:
                measurements.append(measurement)
    return ImportStats(database.add_measurements(iter(measurements)), skipped)


def import_excel_telemetry(database: AuditDatabase, root: Path) -> ImportStats:
    """Загрузить Excel-временные ряды тестового объекта в canonical SQLite."""
    measurements: list[TelemetryMeasurement] = []
    skipped = 0
    for path in root.glob("*.xls*"):
        target = _target(path.name)
        if target is None:
            continue
        (
            plant_code,
            aggregate_code,
            technical_place_code,
            pressure_multiplier,
            pressure_metric,
        ) = target
        if aggregate_code:
            database.upsert_aggregate(
                plant_code,
                aggregate_code,
                "работа",
                technical_place_code=technical_place_code,
            )
        for record in build_excel_telemetry(path, source_root=root).get("telemetry", []):
            measurement = _measurement(
                record,
                plant_code,
                aggregate_code or _aggregate_from_tag(record.get("tag", ""), plant_code),
                technical_place_code,
                pressure_multiplier,
                pressure_metric,
                source_kind="excel",
                source_file=str(path.relative_to(root)),
            )
            if measurement is None:
                skipped += 1
            else:
                measurements.append(measurement)
    return ImportStats(database.add_measurements(iter(measurements)), skipped)


def _target(filename: str) -> tuple[str, str | None, str, float, str | None] | None:
    if "КНС-10 БН" in filename:
        return "kns10bn", _aggregate_from_filename(filename), "main", 0.101325, None
    if "КНС-54" in filename:
        aggregate = None if "бг" in filename.lower() else _aggregate_from_filename(filename)
        pressure_metric = "p_bg" if aggregate is None and "бг" in filename.lower() else None
        return "kns54an", aggregate, "main", 0.0980665, pressure_metric
    if "КНС-ОПУ" in filename or "КНС ОПУ" in filename:
        lower_filename = filename.lower()
        aggregate = (
            None
            if "бг" in lower_filename or "проток" in lower_filename
            else _aggregate_from_filename(filename)
        )
        pressure_metric = "p_bg" if aggregate is None and "бг" in lower_filename else None
        return "knsopu", aggregate, "main", 0.0980665, pressure_metric
    if "КНС-97 ПР ЕН" in filename:
        aggregate = None if "бг" in filename.lower() else _aggregate_from_filename(filename)
        if aggregate:
            aggregate = f"{aggregate} ПР"
        pressure_metric = "p_bg" if aggregate is None and "бг" in filename.lower() else None
        return "kns97pren", aggregate, "main", 1.0, pressure_metric
    if "КНС-97 ЕН" in filename:
        aggregate = None if "бг" in filename.lower() else _aggregate_from_filename(filename)
        pressure_metric = "p_bg" if aggregate is None and "бг" in filename.lower() else None
        return "kns97pren", aggregate, "main", 1.0, pressure_metric
    return None


def _aggregate_from_filename(filename: str) -> str | None:
    for aggregate in ("НА-03", "НА-02", "НА-1", "НА-2", "НА-3"):
        if aggregate in filename:
            return {"НА-03": "НА-3", "НА-02": "НА-2"}.get(aggregate, aggregate)
    return None


def _aggregate_from_tag(tag: str, plant_code: str) -> str | None:
    normalized = tag.upper().replace(" ", "-")
    if plant_code == "kns10bn" and normalized in {"НА-1", "НА-2"}:
        return normalized
    if plant_code == "kns54an" and normalized in {"НА-1", "НА-2"}:
        return normalized
    if plant_code == "knsopu" and normalized in {"НА-1", "НА-2", "НА-3"}:
        return normalized
    if plant_code == "kns97pren":
        if normalized.startswith("НА-01") or normalized.startswith("НА-1"):
            return "НА-1"
        if normalized.startswith("НА-03") or normalized.startswith("НА-3"):
            return "НА-3"
        if normalized.startswith(("НА-2", "НА-02")):
            return "НА-2 ПР"
    return None


def _measurement(
    record: dict,
    plant_code: str,
    aggregate_code: str | None,
    technical_place_code: str,
    pressure_multiplier: float,
    pressure_metric: str | None,
    *,
    source_kind: str,
    source_file: str,
) -> TelemetryMeasurement | None:
    if record.get("value") is None:
        return None
    metric, unit = _metric(record, pressure_metric)
    if metric is None:
        return None
    return TelemetryMeasurement(
        plant_code=plant_code,
        aggregate_code=aggregate_code,
        timestamp=datetime.fromisoformat(record["timestamp"]),
        metric=metric,
        value=float(record["value"]) * (pressure_multiplier if metric.startswith("p_") else 1.0),
        unit=unit,
        quality=str(record["quality"]) if record.get("quality") not in (None, "") else None,
        technical_place_code=technical_place_code,
        source_kind=source_kind,
        source_file=source_file,
        source_sheet=record.get("sheet"),
        source_row=int(record["row"]) if record.get("row") is not None else None,
        source_tag=record.get("tag"),
        source_label=record.get("label"),
    )


def _metric(record: dict, pressure_metric: str | None = None) -> tuple[str | None, str]:
    raw_metric = record.get("metric", "")
    label = record.get("label", "").lower()
    if raw_metric == "pressure":
        if pressure_metric:
            return pressure_metric, "МПа"
        if "приём" in label or "прием" in label:
            return "p_in", "МПа"
        if "выкид" in label:
            return "p_out", "МПа"
        if "бг" in label:
            return "p_bg", "МПа"
    if raw_metric == "power_kw":
        return "power", "кВт"
    if raw_metric == "runtime_h":
        return "runtime", "ч"
    if raw_metric == "flow" and "расход" in label:
        return "q_day", "м³/сут"
    if raw_metric == "energy_kwh" and "уд." not in label:
        return "energy", "кВт·ч"
    return None, ""
