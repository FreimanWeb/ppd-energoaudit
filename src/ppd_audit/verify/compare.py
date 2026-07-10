"""Сравнение результата модели с эталоном из «… расчет.xlsx»."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Optional

from ..core.audit import AuditResult
from ..spec import ReferenceOutputs

OK, WARN, FAIL, NA = "✓", "⚠", "✗", "—"


@dataclass
class MetricRow:
    object_id: str
    object_name: str
    water_type: str
    aggregate_id: str
    pump_kind: str
    metric: str
    model: Optional[float]
    reference: Optional[float]
    abs_dev: Optional[float]
    rel_dev: Optional[float]      # доля (0.05 = 5%)
    tolerance: float
    status: str


# Метрика: (ключ, подпись, доступ к модели, доступ к эталону)
_METRICS: list[tuple[str, str, Callable[[AuditResult], Optional[float]],
                     Callable[[ReferenceOutputs], Optional[float]]]] = [
    ("sec_fact", "УРЭ факт, кВт·ч/м³", lambda r: r.sec_fact, lambda o: o.sec_fact),
    ("sec_calc", "УРЭ расчётный, кВт·ч/м³", lambda r: r.sec_calc, lambda o: o.sec_calc),
    ("eta_fact", "КПД факт", lambda r: r.regime.eta_unit, lambda o: o.eta_fact),
    ("eta_nom", "КПД номинальный", lambda r: r.regime.eta_nom, lambda o: o.eta_nom),
    ("load_factor", "K загрузки ЭД", lambda r: r.load_factor, lambda o: o.load_factor),
    ("h_fact", "Напор факт, м", lambda r: r.regime.h_fact, lambda o: o.h_fact),
    ("dw_efficiency", "ΔW КПД, кВт·ч/год", lambda r: r.dw_efficiency, lambda o: o.dw_efficiency),
    ("dw_throttle", "ΔW дрос, кВт·ч/год", lambda r: r.dw_throttle, lambda o: o.dw_throttle),
]


def _status(rel: Optional[float], tol: float) -> str:
    if rel is None:
        return NA
    a = abs(rel)
    if a <= tol:
        return OK
    if a <= 2.0 * tol:
        return WARN
    return FAIL


def compare_aggregate(obj_id: str, obj_name: str, water: str,
                      res: AuditResult, ref: ReferenceOutputs,
                      tolerances: dict, default_tol: float = 0.05) -> list[MetricRow]:
    """Список построчных сравнений по всем метрикам одного агрегата."""
    rows: list[MetricRow] = []
    for key, label, get_model, get_ref in _METRICS:
        m = get_model(res)
        r = get_ref(ref) if ref else None
        tol = tolerances.get(key, default_tol)
        if m is None or r is None:
            rows.append(MetricRow(obj_id, obj_name, water, res.aggregate_id,
                                  res.pump_kind, label, _round(m), _round(r),
                                  None, None, tol, NA))
            continue
        abs_dev = m - r
        rel_dev = abs_dev / abs(r) if r != 0 else None
        rows.append(MetricRow(obj_id, obj_name, water, res.aggregate_id, res.pump_kind,
                              label, _round(m), _round(r), _round(abs_dev),
                              _round(rel_dev, 4), tol, _status(rel_dev, tol)))
    return rows


def _round(x, nd: int = 3):
    return round(x, nd) if isinstance(x, (int, float)) else x


def row_to_dict(row: MetricRow) -> dict:
    return asdict(row)
