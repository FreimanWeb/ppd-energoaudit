"""Трёхсторонняя сверка: модель ↔ «… расчет.xlsx» ↔ текстовый отчёт (.doc/.docx).

Каждый показатель сводится в одну строку с тремя источниками:
  · модель           — расчётное ядро на входах из xlsx;
  · xlsx             — эталонные выходы инженерного расчёта;
  · отчёт            — значения из таблиц/прозы отчёта (для 2026 — диапазон по датам).

Статусы:
  модель↔xlsx, модель↔отчёт  — попадание в толеранс;
  xlsx↔отчёт                 — флаг согласованности источников (расхождение данных/итераций).

Дополнительно сверяются ОТНОСИТЕЛЬНЫЕ утверждения прозы (Δ УРЭ, снижение КПД в п.п.,
снижение напора в м/%) — модель их воспроизводит из своих величин.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

import yaml

from ..config import project_root
from ..core.audit import AuditResult, audit_aggregate
from ..ingest.convert import ensure_report_docx
from ..ingest.report_calc import parse_calc_file
from ..ingest.report_doc import AggregateReport, ObjectReport, parse_report
from ..spec import ReferenceOutputs

OK, WARN, FAIL, NA = "✓", "⚠", "✗", "—"


@dataclass
class ReconRow:
    object_id: str
    object_name: str
    water_type: str
    aggregate_id: str
    pump_kind: str
    kind: str                      # 'абс' | 'отн'
    metric: str
    model: Optional[float]
    xlsx: Optional[float]
    report: Optional[float]        # представительное (для 2026 — последняя дата)
    report_lo: Optional[float]
    report_hi: Optional[float]
    st_model_xlsx: str
    st_model_report: str
    st_sources: str                # xlsx ↔ отчёт (согласованность источников)
    tolerance: float
    note: str


def _rng_dev(v: Optional[float], lo: Optional[float], hi: Optional[float]) -> Optional[float]:
    """Знаковое относительное отклонение v от диапазона [lo,hi] (0, если внутри)."""
    if v is None or lo is None or hi is None:
        return None
    mid = (lo + hi) / 2.0
    if lo <= v <= hi:
        return 0.0
    edge = lo if v < lo else hi
    return (v - edge) / abs(mid) if mid else None


def _status(v: Optional[float], lo: Optional[float], hi: Optional[float],
            rel_tol: float, abs_floor: float = 0.0) -> tuple[str, Optional[float]]:
    """Статус попадания v в [lo,hi]±допуск; возвращает (статус, отн.откл)."""
    if v is None or lo is None or hi is None:
        return NA, None
    mid = (lo + hi) / 2.0
    edge = lo if v < lo else (hi if v > hi else v)
    abs_dev = v - edge
    if abs(abs_dev) <= abs_floor:
        return OK, 0.0
    rel = _rng_dev(v, lo, hi)
    if rel is None:
        return NA, None
    a = abs(rel)
    return (OK if a <= rel_tol else WARN if a <= 2 * rel_tol else FAIL), rel


# Абсолютные метрики: (поле, подпись, getter модели, getter xlsx, поле отчёта).
_ABS: list[tuple[str, str, Callable[[AuditResult], Optional[float]],
                 Callable[[ReferenceOutputs], Optional[float]], str]] = [
    ("sec_fact", "УРЭ факт, кВт·ч/м³", lambda r: r.sec_fact, lambda o: o.sec_fact, "sec_fact"),
    ("sec_calc", "УРЭ расчётный, кВт·ч/м³", lambda r: r.sec_calc, lambda o: o.sec_calc, "sec_calc"),
    ("eta_fact", "КПД факт", lambda r: r.regime.eta_unit, lambda o: o.eta_fact, "eta_fact"),
    ("eta_nom", "КПД номинальный", lambda r: r.regime.eta_nom, lambda o: o.eta_nom, "eta_nom"),
    ("load_factor", "K загрузки ЭД", lambda r: r.load_factor, lambda o: o.load_factor, "load_factor"),
    ("h_fact", "Напор факт, м", lambda r: r.regime.h_fact, lambda o: o.h_fact, "h_fact"),
    ("dw_efficiency", "ΔW КПД, кВт·ч/год", lambda r: r.dw_efficiency, lambda o: o.dw_efficiency, "dw_efficiency"),
]


def _model_relative(res: AuditResult) -> dict[str, Optional[float]]:
    """Относительные показатели, вычисленные из величин модели (для сверки с прозой)."""
    out: dict[str, Optional[float]] = {}
    en, ef = res.regime.eta_nom, res.regime.eta_unit
    out["eta_reduction_pp"] = (en - ef) * 100 if en is not None and ef is not None else None
    out["sec_over_calc"] = (res.sec_fact - res.sec_calc
                            if res.sec_fact is not None and res.sec_calc is not None else None)
    if res.h_due and res.regime.h_fact is not None:
        out["head_drop_m"] = res.h_due - res.regime.h_fact
        out["head_drop_pct"] = (res.h_due - res.regime.h_fact) / res.h_due * 100
    else:
        out["head_drop_m"] = None
        out["head_drop_pct"] = None
    return out


_REL_LABELS = {
    "eta_reduction_pp": "КПД снижен, п.п.",
    "sec_over_calc": "УРЭ выше расч., кВт·ч/м³",
    "head_drop_pct": "Напор ниже Q-H, %",
    "head_drop_m": "Напор ниже Q-H, м",
}


def reconcile_aggregate(obj_id, obj_name, water, res: AuditResult,
                        xlsx_ref: Optional[ReferenceOutputs],
                        rep_agg: Optional[AggregateReport],
                        tol: dict, rep_tol: dict) -> list[ReconRow]:
    rows: list[ReconRow] = []

    # ---- абсолютные показатели (три источника) ----
    for key, label, gm, go, rfield in _ABS:
        m = gm(res)
        x = go(xlsx_ref) if xlsx_ref else None
        rep_rng = rep_agg.range_of(rfield) if rep_agg else None
        rep_val = getattr(rep_agg.reference, rfield) if rep_agg else None
        t = tol.get(key, 0.05)
        st_mx = _status(m, x, x, t)[0] if x is not None else NA
        st_mr = _status(m, *rep_rng, t)[0] if rep_rng else NA
        st_src = _status(x, *rep_rng, t)[0] if (x is not None and rep_rng) else NA
        note = _explain(key, st_mx, st_mr, st_src, obj_id, res, x, rep_rng)
        rows.append(ReconRow(
            obj_id, obj_name, water, res.aggregate_id, res.pump_kind, "абс", label,
            _r(m), _r(x), _r(rep_val),
            _r(rep_rng[0]) if rep_rng else None, _r(rep_rng[1]) if rep_rng else None,
            st_mx, st_mr, st_src, t, note))

    # ---- относительные утверждения прозы (модель ↔ отчёт) ----
    if rep_agg:
        mrel = _model_relative(res)
        claims_by_metric: dict[str, list] = {}
        for c in rep_agg.claims:
            claims_by_metric.setdefault(c.metric, []).append(c)
        for metric, label in _REL_LABELS.items():
            claims = claims_by_metric.get(metric)
            if not claims:
                continue
            lo = min(c.value_min for c in claims)
            hi = max(c.value_max for c in claims)
            m = mrel.get(metric)
            rel_tol, abs_floor = rep_tol.get(metric, [0.10, 0.0])
            st_mr, _ = _status(m, lo, hi, rel_tol, abs_floor)
            note = "" if st_mr in (OK, NA) else "модель вне диапазона прозы (методика/округление/дата)"
            if m is None:
                note = "модель не считает (нет кривой Q-H / нет должного напора)"
            rows.append(ReconRow(
                obj_id, obj_name, water, res.aggregate_id, res.pump_kind, "отн", label,
                _r(m), None, _r((lo + hi) / 2), _r(lo), _r(hi),
                NA, st_mr, NA, rel_tol, note))
    return rows


# Контекст расхождения источников по объекту (разбор причины для Task 1.5).
_OBJECT_CONTEXT = {
    "knsopu": "отчёт — ряд замеров март–апр 2026, xlsx — отдельный снимок; привязка ЦНС-63/80 и η_ном (0,577) различаются",
    "kns14an": "в xlsx тип/порядок агрегатов (REDA ↔ СИН) отличается от отчёта",
    "kns10bn": "в отчёте р_вых в «исходных данных» (8,92 МПа→703 м) и «тех.параметрах» (949 м) различаются; xlsx — по 8,92",
}


def _explain(key, st_mx, st_mr, st_src, obj_id, res, x, rep_rng) -> str:
    if st_mx == OK and st_mr in (OK, NA) and st_src in (OK, NA):
        return ""
    ctx = _OBJECT_CONTEXT.get(obj_id, "")
    if st_src in (WARN, FAIL):
        base = "источники расходятся (xlsx ≠ отчёт)"
        return f"{base}: {ctx}" if ctx else f"{base}: разные итерации/правки расчёта"
    if key == "eta_nom" and st_mx in (WARN, FAIL):
        return "η_ном: модель берёт паспорт насоса, в xlsx — упрощение/«залип» (см. docs)"
    if key in ("sec_calc", "dw_efficiency") and st_mx in (WARN, FAIL):
        return "зависит от η_ном (см. строку КПД номинальный)"
    if st_mr in (WARN, FAIL):
        return f"модель vs отчёт: иной замер/округление в отчёте{(' — ' + ctx) if ctx else ''}"
    return ""


def _r(x, nd: int = 3):
    return round(x, nd) if isinstance(x, (int, float)) else x


# ───────────────────────────── прогон по манифесту ─────────────────────────────


def _load_manifest() -> dict:
    with (project_root() / "config" / "verification.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_reconciliation() -> dict:
    """Трёхсторонняя сверка по всем объектам манифеста с отчётом."""
    man = _load_manifest()
    base = project_root() / man["base_dir"]
    tol = man.get("tolerances", {})
    rep_tol = man.get("report_tolerances", {})
    reports_dir = project_root() / "data" / "reports"

    rows: list[ReconRow] = []
    reports: dict[str, ObjectReport] = {}
    errors: list[str] = []

    for obj in man["objects"]:
        if "report" not in obj:
            continue
        xlsx_path = base / obj["file"]
        rep_src = base / obj["report"]
        if not xlsx_path.exists():
            errors.append(f"{obj['id']}: нет xlsx {xlsx_path}")
            continue
        if not rep_src.exists():
            errors.append(f"{obj['id']}: нет отчёта {rep_src}")
            continue
        try:
            spec = parse_calc_file(xlsx_path, obj["id"], obj["name"])
        except Exception as e:                       # noqa: BLE001
            errors.append(f"{obj['id']}: ошибка парсинга xlsx — {e}")
            continue
        try:
            docx = ensure_report_docx(rep_src, reports_dir / f"{obj['id']}.docx")
            report = parse_report(docx, obj["id"], obj["name"],
                                  water_type=spec.water_type, source_original=str(rep_src))
        except Exception as e:                       # noqa: BLE001
            errors.append(f"{obj['id']}: ошибка парсинга отчёта — {e}")
            continue
        reports[obj["id"]] = report

        for agg in spec.working_aggregates():
            try:
                res = audit_aggregate(agg, spec.branch)
            except Exception as e:                   # noqa: BLE001
                errors.append(f"{obj['id']}/{agg.id}: ошибка расчёта — {e}")
                continue
            rep_agg = report.aggregate(agg.id)
            rows.extend(reconcile_aggregate(
                obj["id"], obj["name"], spec.water_type.value, res,
                agg.reference, rep_agg, tol, rep_tol))

    return {"rows": rows, "reports": reports, "errors": errors,
            "summary": _summary(rows)}


def _summary(rows: list[ReconRow]) -> dict:
    def count(attr):
        c = {OK: 0, WARN: 0, FAIL: 0, NA: 0}
        for r in rows:
            c[getattr(r, attr)] = c.get(getattr(r, attr), 0) + 1
        return c
    src = [r for r in rows if r.st_sources != NA]
    src_ok = sum(1 for r in src if r.st_sources == OK)
    return {
        "total_rows": len(rows),
        "model_xlsx": count("st_model_xlsx"),
        "model_report": count("st_model_report"),
        "sources": count("st_sources"),
        "source_pairs": len(src),
        "source_agreement_rate": round(src_ok / len(src), 3) if src else None,
    }


_CSV_FIELDS = ["object_id", "object_name", "water_type", "aggregate_id", "pump_kind",
               "kind", "metric", "model", "xlsx", "report", "report_lo", "report_hi",
               "st_model_xlsx", "st_model_report", "st_sources", "tolerance", "note"]


def save_reconciliation(result: dict, root: Path | None = None) -> dict:
    """Записать data/generated/reconciliation_reports.{csv,md}."""
    root = root or project_root()
    out = root / "data" / "generated"
    out.mkdir(parents=True, exist_ok=True)
    rows = [asdict(r) for r in result["rows"]]

    csv_path = out / "reconciliation_reports.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)

    md_path = out / "reconciliation_reports.md"
    md_path.write_text(_to_markdown(result), encoding="utf-8")
    return {"csv": csv_path, "md": md_path}


def _fmt(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:,.3f}".replace(",", " ").replace(".", ",").rstrip("0").rstrip(",")
    return str(x)


def _to_markdown(result: dict) -> str:
    s = result["summary"]
    lines = ["# Трёхсторонняя сверка: модель ↔ расчет.xlsx ↔ отчёт",
             "",
             f"Строк: **{s['total_rows']}**. Согласованность источников (xlsx↔отчёт): "
             f"**{s['source_agreement_rate']:.0%}** из {s['source_pairs']} пар."
             if s["source_agreement_rate"] is not None else f"Строк: {s['total_rows']}.",
             "",
             f"- Модель↔xlsx: ✓ {s['model_xlsx'][OK]} · ⚠ {s['model_xlsx'][WARN]} · ✗ {s['model_xlsx'][FAIL]}",
             f"- Модель↔отчёт: ✓ {s['model_report'][OK]} · ⚠ {s['model_report'][WARN]} · ✗ {s['model_report'][FAIL]}",
             f"- Источники (xlsx↔отчёт): ✓ {s['sources'][OK]} · ⚠ {s['sources'][WARN]} · ✗ {s['sources'][FAIL]}",
             ""]
    if result["errors"]:
        lines += ["## Ошибки парсинга", *[f"- {e}" for e in result["errors"]], ""]

    by_obj: dict[tuple, list] = {}
    for r in result["rows"]:
        by_obj.setdefault((r.object_id, r.object_name, r.aggregate_id, r.pump_kind), []).append(r)

    for (oid, name, agg, kind), rs in by_obj.items():
        lines.append(f"## {name} · {agg} ({kind})")
        lines.append("")
        lines.append("| Показатель | Модель | xlsx | Отчёт | М↔xlsx | М↔отч | Ист. | Примечание |")
        lines.append("|---|---|---|---|:--:|:--:|:--:|---|")
        for r in rs:
            rep = (_fmt(r.report) if r.report_lo == r.report_hi
                   else f"{_fmt(r.report_lo)}…{_fmt(r.report_hi)}")
            lines.append(f"| {r.metric} | {_fmt(r.model)} | {_fmt(r.xlsx)} | {rep} | "
                         f"{r.st_model_xlsx} | {r.st_model_report} | {r.st_sources} | {r.note} |")
        rep = result["reports"].get(oid)
        if rep:
            ra = rep.aggregate(agg)
            if ra and ra.claims:
                seen_q, uniq = set(), []
                for c in ra.claims:
                    if c.text and c.text not in seen_q:
                        seen_q.add(c.text)
                        uniq.append(c.text)
                lines.append("")
                lines.append("_Цитаты отчёта:_ " + " · ".join(f"«{t}»" for t in uniq[:3]))
        lines.append("")
    return "\n".join(lines)
