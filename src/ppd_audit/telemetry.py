"""Primary telemetry contract and minimal mapping to calculation inputs."""

from __future__ import annotations

import json
import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .spec import RegimeMeasurement


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().replace("ё", "е"))


class TelemetryRecord(BaseModel):
    timestamp: datetime
    tag: str
    metric: str
    value: float
    label: str = ""
    unit: str = ""
    quality: Any = None
    source_file: str | None = None
    sheet: str | None = None
    row: int | None = None


class AggregationPeriod(StrEnum):
    two_hours = "2h"
    day = "day"
    month = "month"
    year = "year"


class RawTelemetryMetric(StrEnum):
    p_in = "p_in"
    p_out = "p_out"
    p_bg = "p_bg"
    flow_rate = "flow_rate"
    q_day = "q_day"
    runtime = "runtime"
    energy = "energy"
    power = "power"
    t_year = "t_year"
    q_year = "q_year"
    level = "level"
    pump_state = "pump_state"
    density = "density"
    viscosity = "viscosity"


def _unit_key(value: str) -> str:
    return _norm(value).replace("³", "3").replace("²", "2").replace("·", "*").replace(" ", "")


_METRIC_UNITS: dict[RawTelemetryMetric, dict[str, tuple[str, float]]] = {
    RawTelemetryMetric.p_in: {"мпа": ("МПа", 1), "кгс/см2": ("МПа", 0.098)},
    RawTelemetryMetric.p_out: {"мпа": ("МПа", 1), "кгс/см2": ("МПа", 0.098)},
    RawTelemetryMetric.p_bg: {"мпа": ("МПа", 1), "кгс/см2": ("МПа", 0.098)},
    RawTelemetryMetric.flow_rate: {"м3/ч": ("м³/ч", 1)},
    RawTelemetryMetric.q_day: {"м3/сут": ("м³/сут", 1)},
    RawTelemetryMetric.runtime: {"ч": ("ч", 1)},
    RawTelemetryMetric.energy: {"квт*ч/сут": ("кВт·ч/сут", 1)},
    RawTelemetryMetric.power: {"квт": ("кВт", 1)},
    RawTelemetryMetric.t_year: {"ч": ("ч", 1)},
    RawTelemetryMetric.q_year: {"м3/год": ("м³/год", 1)},
    RawTelemetryMetric.level: {"мм": ("мм", 1)},
    RawTelemetryMetric.pump_state: {"": ("", 1)},
    RawTelemetryMetric.density: {"кг/м3": ("кг/м³", 1)},
    RawTelemetryMetric.viscosity: {"сст": ("сСт", 1)},
}

_METRIC_LABELS = {
    RawTelemetryMetric.p_in: "Давление на приёме насоса",
    RawTelemetryMetric.p_out: "Давление на выкиде насоса",
    RawTelemetryMetric.p_bg: "Давление на БГ",
    RawTelemetryMetric.flow_rate: "Мгновенный расход жидкости",
    RawTelemetryMetric.q_day: "Суточная перекачка",
    RawTelemetryMetric.runtime: "Время работы за сутки",
    RawTelemetryMetric.energy: "Расход электроэнергии",
    RawTelemetryMetric.power: "Активная мощность",
    RawTelemetryMetric.t_year: "Годовая наработка",
    RawTelemetryMetric.q_year: "Годовой объём перекачки",
    RawTelemetryMetric.level: "Уровень буферной ёмкости",
    RawTelemetryMetric.pump_state: "Состояние насоса",
    RawTelemetryMetric.density: "Плотность жидкости",
    RawTelemetryMetric.viscosity: "Вязкость",
}


class RawTelemetryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    aggregate_id: str = Field(min_length=1)
    metric: RawTelemetryMetric
    unit: str
    value: float

    @model_validator(mode="after")
    def normalize_unit(self) -> "RawTelemetryRecord":
        try:
            canonical_unit, multiplier = _METRIC_UNITS[self.metric][_unit_key(self.unit)]
        except KeyError as exc:
            raise ValueError(f"недопустимая единица {self.unit!r} для {self.metric.value}") from exc
        self.unit = canonical_unit
        self.value *= multiplier
        return self


class TelemetrySubmission(BaseModel):
    """Строгий вход HTTP-контракта: только raw inputs, без расчётных KPI."""

    model_config = ConfigDict(extra="forbid")

    object_id: str = Field(min_length=1)
    technical_place: str = Field(min_length=1)
    injection_agent: str | None = None
    aggregation_period: AggregationPeriod
    records: list[RawTelemetryRecord] = Field(min_length=1)

    def to_payload(self) -> "TelemetryPayload":
        source = self.model_dump(exclude={"records"}, mode="json")
        return TelemetryPayload(
            source=source,
            records=[
                TelemetryRecord(
                    timestamp=record.timestamp,
                    tag=record.aggregate_id,
                    metric=record.metric.value,
                    label=_METRIC_LABELS[record.metric],
                    unit=record.unit,
                    value=record.value,
                )
                for record in self.records
            ],
        )


class TelemetryPayload(BaseModel):
    schema_version: Literal["telemetry.v1"] = Field(
        "telemetry.v1", validation_alias="schema", serialization_alias="schema"
    )
    source: dict[str, Any] = Field(default_factory=dict)
    records: list[TelemetryRecord] = Field(default_factory=list)

    @property
    def schema(self) -> str:  # type: ignore[override]
        return self.schema_version


class TelemetryIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    field: str | None = None
    record_index: int | None = None


class TelemetryValidationReport(BaseModel):
    ok: bool
    total_records: int
    by_metric: dict[str, int]
    issues: list[TelemetryIssue] = Field(default_factory=list)


class NormalizedCalculationInput(BaseModel):
    tag: str | None = None
    rho: float | None = None
    p_in: float | None = None
    p_out: float | None = None
    q_day: float | None = None
    t: float | None = None
    w: float | None = None
    q_fact: float | None = None
    p_electric: float | None = None
    p_bg: float | None = None
    nu: float | None = None
    t_year: float | None = None
    q_year: float | None = None
    sources: dict[str, str] = Field(default_factory=dict)

    def to_regime(self) -> RegimeMeasurement:
        rho, p_in, p_out = self.rho, self.p_in, self.p_out
        if rho is None or p_in is None or p_out is None:
            raise ValueError("нет обязательных полей режима: rho, p_in, p_out")
        return RegimeMeasurement(
            rho=rho,
            p_in=p_in,
            p_out=p_out,
            q_day=self.q_day,
            t=self.t,
            w=self.w,
            q_fact=self.q_fact,
            p_electric=self.p_electric,
            p_bg=self.p_bg,
            nu=self.nu,
            t_year=self.t_year,
        )


class TelemetryValidationResponse(BaseModel):
    validation: TelemetryValidationReport
    normalized_by_aggregate: dict[str, NormalizedCalculationInput]


def telemetry_payload_from_excel_draft(draft: dict) -> TelemetryPayload:
    source = draft.get("source", {})
    source_file = source.get("relative_path") or source.get("path")
    records = []
    for item in draft.get("telemetry", []):
        rec = dict(item)
        rec.setdefault("source_file", source_file)
        records.append(TelemetryRecord.model_validate(rec))
    return TelemetryPayload(source=source, records=records)


def telemetry_payload_from_excel_draft_file(path: Path) -> TelemetryPayload:
    return telemetry_payload_from_excel_draft(json.loads(path.read_text(encoding="utf-8")))


def export_telemetry_validation_summary(draft_root: Path, out_path: Path) -> Path:
    files = []
    total_records = 0
    ok_files = 0
    errors = 0
    warnings = 0
    for path in sorted(draft_root.rglob("*.json")):
        payload = telemetry_payload_from_excel_draft_file(path)
        validation = validate_telemetry(payload)
        normalized = map_telemetry_to_calculation_input(payload)
        total_records += validation.total_records
        ok_files += int(validation.ok)
        errors += sum(1 for issue in validation.issues if issue.severity == "error")
        warnings += sum(1 for issue in validation.issues if issue.severity == "warning")
        files.append({
            "path": str(path.relative_to(draft_root)),
            "source": payload.source,
            "validation": validation.model_dump(mode="json"),
            "normalized_input": normalized.model_dump(mode="json", exclude_none=True),
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "schema": "telemetry.validation.v1",
                "summary": {
                    "total_files": len(files),
                    "ok_files": ok_files,
                    "total_records": total_records,
                    "errors": errors,
                    "warnings": warnings,
                },
                "files": files,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return out_path


def validate_telemetry(payload: TelemetryPayload) -> TelemetryValidationReport:
    by_metric: dict[str, int] = {}
    issues: list[TelemetryIssue] = []
    unknown_unit_metrics: set[str] = set()
    for i, rec in enumerate(payload.records):
        by_metric[rec.metric] = by_metric.get(rec.metric, 0) + 1
        if rec.value == 0 and _norm(rec.metric) != "pump_state":
            issues.append(
                TelemetryIssue(
                    severity="warning",
                    code="zero_is_missing",
                    field=rec.metric,
                    message="Нулевое значение трактуется как нет данных",
                    record_index=i,
                )
            )
        if (
            rec.metric in {"pressure", "pressure_mpa", "flow"}
            and not rec.unit
            and rec.metric not in unknown_unit_metrics
        ):
            unknown_unit_metrics.add(rec.metric)
            issues.append(
                TelemetryIssue(
                    severity="warning",
                    code="unknown_unit",
                    field=rec.metric,
                    message="Не указана единица измерения telemetry metric",
                    record_index=i,
                )
            )

    mapped = map_telemetry_to_calculation_input(payload)
    if not payload.records:
        issues.append(
            TelemetryIssue(severity="error", code="no_records", message="Нет telemetry records")
        )
    if mapped.p_in is None:
        issues.append(
            TelemetryIssue(
                severity="error",
                code="missing_pressure_in",
                field="p_in",
                message="Нет давления на входе",
            )
        )
    if mapped.p_out is None:
        issues.append(
            TelemetryIssue(
                severity="error",
                code="missing_pressure_out",
                field="p_out",
                message="Нет давления на выходе",
            )
        )
    if mapped.rho is None:
        issues.append(
            TelemetryIssue(
                severity="error", code="missing_density", field="rho", message="Нет плотности"
            )
        )
    if mapped.q_day is None and mapped.q_fact is None:
        issues.append(
            TelemetryIssue(
                severity="error",
                code="missing_flow",
                field="q_day",
                message="Нет расхода/перекачки",
            )
        )
    if mapped.w is None and mapped.p_electric is None:
        issues.append(
            TelemetryIssue(
                severity="error",
                code="missing_energy",
                field="w",
                message="Нет энергии или электрической мощности",
            )
        )

    return TelemetryValidationReport(
        ok=not any(issue.severity == "error" for issue in issues),
        total_records=len(payload.records),
        by_metric=by_metric,
        issues=issues,
    )


def map_telemetry_to_calculation_input(
    payload: TelemetryPayload, tag: str | None = None
) -> NormalizedCalculationInput:
    out = NormalizedCalculationInput(tag=tag)
    records = [rec for rec in payload.records if tag is None or rec.tag == tag]
    for rec in sorted(records, key=lambda r: r.timestamp):
        if rec.value == 0 and _norm(rec.metric) != "pump_state":
            continue
        field = _field_for(rec)
        if not field:
            continue
        setattr(out, field, rec.value)
        out.sources[field] = _source_ref(rec)
        if out.tag is None:
            out.tag = rec.tag
    return out


def _source_ref(rec: TelemetryRecord) -> str:
    parts = [p for p in (rec.source_file, rec.sheet, str(rec.row) if rec.row else None) if p]
    return ":".join(parts)


def _field_for(rec: TelemetryRecord) -> str | None:
    metric = _norm(rec.metric)
    label = _norm(rec.label)
    unit = _norm(rec.unit)
    if metric in {"p_in", "p_out", "p_bg", "q_day", "q_year", "t_year", "nu"}:
        return metric
    if metric == "flow_rate":
        return "q_fact"
    if metric == "runtime":
        return "t"
    if metric == "energy":
        return "w"
    if metric == "power":
        return "p_electric"
    if metric == "density":
        return "rho"
    if metric == "viscosity":
        return "nu"
    if metric == "power_kw":
        return "p_electric"
    if metric == "energy_kwh":
        return "w"
    if metric == "runtime_h":
        return "t"
    if metric == "density_kg_m3":
        return "rho"
    if metric.startswith("flow"):
        if "/ч" in unit or "м3/ч" in unit or "производ" in label:
            return "q_fact"
        return "q_day"
    if metric.startswith("pressure"):
        if any(x in label for x in ("вход", "вх", "прием", "приеме")):
            return "p_in"
        if any(x in label for x in ("выход", "вых", "выкид")):
            return "p_out"
        if "бг" in label or "коллектор" in label:
            return "p_bg"
    return None
