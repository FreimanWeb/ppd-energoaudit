"""Read-only review of pump characteristics from Ramil's «Уравнения» sheet.

This is a candidate comparison, not approval of a passport or an import into the DB.
Run with --help for the required source, model and target aggregate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import openpyxl

from ..core.audit import audit_aggregate
from ..core.curves import eta_due, head_due, poly2
from ..spec import PumpKind, load_object_spec


@dataclass(frozen=True)
class CandidateCurve:
    model: str
    q_min: float
    q_max: float
    head: tuple[float, float, float]
    eta: tuple[float, float, float]  # fraction, not the workbook's percent
    row: int
    sha256: str

    def contains(self, flow: float) -> bool:
        return math.isfinite(flow) and self.q_min <= flow <= self.q_max

    def points(self) -> tuple[list[list[float]], list[list[float]]]:
        flows = (self.q_min, (self.q_min + self.q_max) / 2, self.q_max)
        return (
            [[q, poly2(q, self.head)] for q in flows],
            [[q, poly2(q, self.eta)] for q in flows],
        )


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Expected a numeric literal in the curve table, got {value!r}")
    if not math.isfinite(value):
        raise ValueError("Curve values must be finite")
    return float(value)


def read_candidate(path: Path, model: str) -> CandidateCurve:
    data = path.read_bytes()
    book = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=False)
    try:
        if "Уравнения" not in book.sheetnames:
            raise ValueError("No «Уравнения» sheet in the workbook")
        sheet = book["Уравнения"]
        headers = [sheet.cell(2, c).value for c in range(1, 12)]
        if headers[:3] != ["Тип насоса", "Минимальная подача, м³/ч", "Максимальная подача, м³/ч"]:
            raise ValueError("Unexpected model/flow columns in «Уравнения»")
        if headers[5:] != ["aH", "bH", "cH", "aη", "bη", "cη"]:
            raise ValueError("Unexpected coefficient columns in «Уравнения»")
        matches = [
            (index, row)
            for index, row in enumerate(
                sheet.iter_rows(min_row=3, max_col=11, values_only=True), start=3
            )
            if row[0] == model
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one row for {model!r}, found {len(matches)}")
        index, row = matches[0]
        curve = CandidateCurve(
            model=model,
            q_min=_number(row[1]),
            q_max=_number(row[2]),
            head=(_number(row[5]), _number(row[6]), _number(row[7])),
            eta=(_number(row[8]) / 100, _number(row[9]) / 100, _number(row[10]) / 100),
            row=index,
            sha256=hashlib.sha256(data).hexdigest(),
        )
        if not 0 <= curve.q_min < curve.q_max:
            raise ValueError("Expected 0 <= Qmin < Qmax")
        # Check extrema too: positive endpoints alone do not guarantee physical curves.
        for coefficients, is_eta in ((curve.head, False), (curve.eta, True)):
            candidates = [curve.q_min, curve.q_max]
            a, b, _ = coefficients
            if a != 0 and curve.contains(-b / (2 * a)):
                candidates.append(-b / (2 * a))
            for q in candidates:
                value = poly2(q, coefficients)
                if not math.isfinite(value) or value <= 0 or (is_eta and value > 1):
                    raise ValueError("Nonphysical head or efficiency within the source range")
        return curve
    finally:
        book.close()


def _model_key(model: str) -> str:
    # Only spelling differences: no fuzzy matching between different impeller trims.
    return model.replace("(", "").replace(")", "").replace(" ", "").casefold()


def compare_candidate(
    path: Path, model: str, object_id: str, aggregate_id: str, flows: list[float] | None = None
) -> dict:
    curve = read_candidate(path, model)
    spec = load_object_spec(object_id)
    aggregate = spec.aggregate(aggregate_id)
    if aggregate.pump.kind != PumpKind.centrifugal:
        raise ValueError("Q-H/Q-eta comparison requires a centrifugal pump")
    if _model_key(aggregate.pump.model) != _model_key(curve.model):
        raise ValueError(f"Different pump models: {aggregate.pump.model!r} and {curve.model!r}")
    if aggregate.regime is None:
        raise ValueError("The target aggregate has no measured regime")
    actual_flow = aggregate.regime.flow()
    selected = flows if flows is not None else [curve.q_min, actual_flow, curve.q_max]
    if not all(math.isfinite(q) for q in selected):
        raise ValueError("Requested flows must be finite")
    qh, qeta = curve.points()
    comparisons = []
    for q in selected:
        inside = curve.contains(q)
        comparisons.append({
            "flow_m3h": q,
            "status": "within_source_range" if inside else "out_of_range",
            "head_m": poly2(q, curve.head) if inside else None,
            "eta_fraction": poly2(q, curve.eta) if inside else None,
            "core_head_m": head_due(q, qh) if inside else None,
            "core_eta_fraction": eta_due(q, qeta) if inside else None,
        })
    baseline = audit_aggregate(aggregate, spec.branch)
    candidate = None
    if curve.contains(actual_flow):
        trial = aggregate.model_copy(deep=True)
        trial.pump.curve_qh, trial.pump.curve_qeta = qh, qeta
        candidate = audit_aggregate(trial, spec.branch)
    return {
        "approval": "pending",
        "source": {
            "file": str(path),
            "sha256": curve.sha256,
            "sheet": "Уравнения",
            "cells": f"A{curve.row}:K{curve.row}",
            "eta_unit_in_workbook": "percent",
        },
        "model": curve.model,
        "source_range_m3h": [curve.q_min, curve.q_max],
        "head_coefficients": curve.head,
        "eta_fraction_coefficients": curve.eta,
        "points": comparisons,
        "current_regime": {
            "object_id": object_id,
            "aggregate_id": aggregate_id,
            "flow_m3h": actual_flow,
            "status": "within_source_range" if candidate else "out_of_range",
            "measured_head_m": baseline.regime.h_fact,
            "current_h_due_m": baseline.h_due,
            "candidate_h_due_m": candidate.h_due if candidate else None,
            "measured_eta_fraction": baseline.eta_pump,
            "candidate_eta_fraction": eta_due(actual_flow, qeta) if candidate else None,
        },
        "limitations": [
            "Source coefficients are not approved passport data for the installed pump.",
            "The source range is not necessarily the recommended operating zone (48 vs 60 m³/h).",
            "Speed and applicability to the installed impeller must be confirmed.",
            "No extrapolation, passport edits or database writes are performed.",
            "Q-eta is compared separately; the KNS loss decomposition is not changed.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--model", required=True, help="Exact model name in the workbook")
    parser.add_argument("--object", dest="object_id", required=True)
    parser.add_argument("--aggregate", required=True)
    parser.add_argument("--flows", nargs="+", type=float)
    args = parser.parse_args(argv)
    try:
        report = compare_candidate(
            args.workbook, args.model, args.object_id, args.aggregate, args.flows
        )
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
