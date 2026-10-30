"""Parameter-value JSON templates for calculation Excel files."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from ..config import project_root
from .report_calc import CellBinding, ParsedCalc, apply_t_year_overrides, parse_calc_file_with_cells


SCHEMA = "ntu.calculation.parameters.v1"

_EXPECTED = {
    "passport": [
        "pump.model",
        "pump.h_nom",
        "pump.q_nom",
        "pump.power_nom",
        "pump.n_rpm",
        "pump.eta_nom",
        "motor.model",
        "motor.p_nom",
        "motor.eta_nom",
        "motor.cos_phi",
        "motor.voltage_kv",
        "motor.i_nom",
        "motor.n_rpm",
    ],
    "input": [
        "rho",
        "p_in",
        "p_out",
        "q_day",
        "t",
        "w",
        "p_electric",
        "q_fact",
        "p_bg",
        "t_year",
    ],
    "reference": [
        "h_fact",
        "h_due",
        "p_hydraulic",
        "eta_fact",
        "eta_nom",
        "sec_fact",
        "sec_calc",
        "load_factor",
        "dw_efficiency",
        "dw_throttle",
    ],
}


def build_parameter_json(parsed: ParsedCalc, source_file: str, source_kind: str) -> dict[str, Any]:
    by_aggregate: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    cells_by_key = {(c.aggregate_id, c.role, c.field): c for c in parsed.cells}
    aggregate_ids = sorted({c.aggregate_id for c in parsed.cells}, key=_natural_key)
    parsed_count = 0
    needs_review_count = 0

    for aggregate_id in aggregate_ids:
        by_aggregate[aggregate_id] = {}
        for role, fields in _EXPECTED.items():
            by_aggregate[aggregate_id][role] = {}
            for field in fields:
                cell = cells_by_key.get((aggregate_id, role, field))
                item = _parameter_item(cell, field)
                parsed_count += item["status"] == "parsed"
                needs_review_count += item["status"] == "needs_review"
                by_aggregate[aggregate_id][role][field] = item

    return {
        "schema": SCHEMA,
        "source": {"file": source_file, "kind": source_kind},
        "status": "parsed" if aggregate_ids else "parsed_empty",
        "object": {
            "id": parsed.spec.id,
            "name": parsed.spec.name,
            "water_type": parsed.spec.water_type.value,
            "branch": parsed.spec.branch.value,
        },
        "summary": {
            "aggregates": len(aggregate_ids),
            "parsed": parsed_count,
            "needs_review": needs_review_count,
        },
        "aggregates": by_aggregate,
    }


def export_calculation_parameter_jsons(
    root: Path | None = None, out_root: Path | None = None
) -> dict[str, Any]:
    root = root or project_root()
    out_root = out_root or root / "data" / "json"
    manifest = _load_manifest(root)
    base = root / manifest["base_dir"]
    sources = _sources_from_manifest(manifest) + _extra_calc_sources(base, manifest)
    written = []
    errors = []

    for source in sources:
        rel = Path(source["file"])
        path = base / rel
        out_path = out_root / rel.with_name(rel.name + ".json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            parsed = parse_calc_file_with_cells(path, source["id"], source["name"])
            apply_t_year_overrides(parsed, source.get("t_year_overrides", {}))
            payload = build_parameter_json(parsed, str(rel), source["kind"])
        except Exception as exc:
            payload = _error_payload(source, exc)
            errors.append({"file": str(rel), "error": str(exc)})
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(str(out_path.relative_to(out_root)))

    index = {
        "schema": "ntu.calculation.parameters.index.v1",
        "total_files": len(written),
        "errors": errors,
        "files": written,
    }
    (out_root / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return index


def _parameter_item(cell: CellBinding | None, field: str) -> dict[str, Any]:
    if cell is None:
        return {
            "value": None,
            "unit": "",
            "label": field,
            "method_ref": "",
            "status": "needs_review",
            "source": {},
        }
    value = cell.value if cell.value is not None else cell.raw
    return {
        "value": value,
        "unit": cell.unit,
        "label": cell.label,
        "method_ref": cell.method_ref,
        "status": "parsed" if value is not None else "needs_review",
        "source": {
            "sheet": cell.sheet,
            "label_cell": cell.label_cell,
            "value_cell": cell.value_cell,
            "raw": cell.raw,
        },
    }


def _load_manifest(root: Path) -> dict[str, Any]:
    with (root / "config" / "verification.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _sources_from_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": obj["id"],
            "name": obj["name"],
            "file": obj["file"],
            "kind": "verification_manifest",
            "t_year_overrides": obj.get("t_year_overrides", {}),
        }
        for obj in manifest["objects"]
    ]


def _extra_calc_sources(base: Path, manifest: dict[str, Any]) -> list[dict[str, str]]:
    known = {obj["file"] for obj in manifest["objects"]}
    out = []
    for path in sorted(base.rglob("*.xlsx")):
        rel = str(path.relative_to(base))
        name = path.name.lower()
        if rel in known or name.startswith("~$") or ("расчет" not in name and "расчёт" not in name):
            continue
        object_id = _slug(path.stem)
        out.append({"id": object_id, "name": path.stem, "file": rel, "kind": "extra_calc_xlsx"})
    return out


def _error_payload(source: dict[str, str], exc: Exception) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source": {"file": source["file"], "kind": source["kind"]},
        "object": {"id": source["id"], "name": source["name"]},
        "summary": {"aggregates": 0, "parsed": 0, "needs_review": 0},
        "status": "parse_error",
        "error": str(exc),
        "aggregates": {},
    }


def _slug(value: str) -> str:
    return re.sub(r"[^a-zа-я0-9]+", "_", value.lower().replace("ё", "е")).strip("_")


def _natural_key(value: str) -> list[Any]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value)]
