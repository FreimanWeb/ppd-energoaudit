"""Прогон верификации: парсинг эталонов → расчёт ядра → сверка → отчёт.

Артефакты:
  config/plants/<id>.yaml          — сгенерированный спец каждого объекта (переиспользуемый);
  data/generated/verification_report.{csv,json}.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from ..config import project_root
from ..core.audit import audit_aggregate
from ..ingest.report_calc import parse_calc_file
from ..spec import ObjectSpec
from ..spec_io import save_object_spec
from .compare import FAIL, MetricRow, OK, WARN, compare_aggregate, row_to_dict


def load_manifest() -> dict:
    with (project_root() / "config" / "verification.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_verification(save_specs: bool = True) -> dict:
    """Прогнать все объекты манифеста, вернуть строки сверки и спецы."""
    man = load_manifest()
    base = project_root() / man["base_dir"]
    tol = man.get("tolerances", {})

    rows: list[MetricRow] = []
    specs: dict[str, ObjectSpec] = {}
    errors: list[str] = []

    for obj in man["objects"]:
        path = base / obj["file"]
        if not path.exists():
            errors.append(f"{obj['id']}: нет файла {path}")
            continue
        try:
            spec = parse_calc_file(path, obj["id"], obj["name"])
        except Exception as e:                       # noqa: BLE001
            errors.append(f"{obj['id']}: ошибка парсинга — {e}")
            continue
        specs[obj["id"]] = spec
        if save_specs:
            save_object_spec(spec)
        for agg in spec.working_aggregates():
            try:
                res = audit_aggregate(agg, spec.branch)
            except Exception as e:                   # noqa: BLE001
                errors.append(f"{obj['id']}/{agg.id}: ошибка расчёта — {e}")
                continue
            rows.extend(compare_aggregate(
                obj["id"], obj["name"], spec.water_type.value, res,
                agg.reference, tol))

    return {"rows": rows, "specs": specs, "errors": errors,
            "summary": _summarize(rows)}


def _summarize(rows: list[MetricRow]) -> dict:
    by_status = {OK: 0, WARN: 0, FAIL: 0, "—": 0}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    measured = [r for r in rows if r.metric.startswith(("УРЭ факт", "КПД факт"))]
    measured_ok = sum(1 for r in measured if r.status == OK)
    return {
        "total_rows": len(rows),
        "by_status": by_status,
        "measured_metrics": len(measured),
        "measured_ok": measured_ok,
        "measured_pass_rate": round(measured_ok / len(measured), 3) if measured else None,
    }


def save_report(result: dict, root: Path | None = None) -> dict:
    """Сохранить verification_report.csv и .json."""
    root = root or project_root()
    out = root / "data" / "generated"
    out.mkdir(parents=True, exist_ok=True)
    rows = [row_to_dict(r) for r in result["rows"]]

    csv_path = out / "verification_report.csv"
    if rows:
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    json_path = out / "verification_report.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump({"summary": result["summary"], "errors": result["errors"], "rows": rows},
                  f, ensure_ascii=False, indent=2)
    return {"csv": csv_path, "json": json_path}
