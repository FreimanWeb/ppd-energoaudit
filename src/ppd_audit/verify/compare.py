"""Сравнение результата модели с эталоном из «… расчет.xlsx»."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from ..core.audit import AuditResult
from ..ingest.report_calc import CellBinding
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
    model: float | None
    reference: float | None
    abs_dev: float | None
    rel_dev: float | None  # доля (0.05 = 5%)
    tolerance: float
    status: str


@dataclass
class CellRow:
    object_id: str
    object_name: str
    water_type: str
    aggregate_id: str
    role: str
    field: str
    label: str
    method_ref: str
    unit: str
    sheet: str
    label_cell: str | None
    value_cell: str | None
    raw: Any
    excel_value: float | None
    model_value: float | None
    abs_dev: float | None
    rel_dev: float | None
    tolerance: float | None
    status: str


# Метрика: (ключ, подпись, доступ к модели, доступ к эталону)
_METRICS: list[
    tuple[
        str,
        str,
        Callable[[AuditResult], float | None],
        Callable[[ReferenceOutputs], float | None],
    ]
] = [
    ("sec_fact", "УРЭ факт, кВт·ч/м³", lambda r: r.sec_fact, lambda o: o.sec_fact),
    ("sec_calc", "УРЭ расчётный, кВт·ч/м³", lambda r: r.sec_calc, lambda o: o.sec_calc),
    ("eta_fact", "КПД факт", lambda r: r.regime.eta_unit, lambda o: o.eta_fact),
    ("eta_nom", "КПД номинальный", lambda r: r.regime.eta_nom, lambda o: o.eta_nom),
    ("load_factor", "K загрузки ЭД", lambda r: r.load_factor, lambda o: o.load_factor),
    ("h_fact", "Напор факт, м", lambda r: r.regime.h_fact, lambda o: o.h_fact),
    ("dw_efficiency", "ΔW КПД, кВт·ч/год", lambda r: r.dw_efficiency, lambda o: o.dw_efficiency),
    ("dw_throttle", "ΔW дрос, кВт·ч/год", lambda r: r.dw_throttle, lambda o: o.dw_throttle),
]


def _status(rel: float | None, tol: float) -> str:
    if rel is None:
        return NA
    a = abs(rel)
    if a <= tol:
        return OK
    if a <= 2.0 * tol:
        return WARN
    return FAIL


_MODEL_BY_FIELD = {key: get_model for key, _label, get_model, _get_ref in _METRICS}
_CELL_MODEL_BY_FIELD = {
    **_MODEL_BY_FIELD,
    "h_due": lambda r: r.h_due,
    "p_hydraulic": lambda r: r.regime.p_hydraulic,
}


def compare_aggregate(
    obj_id: str,
    obj_name: str,
    water: str,
    res: AuditResult,
    ref: ReferenceOutputs | None,
    tolerances: dict,
    default_tol: float = 0.05,
) -> list[MetricRow]:
    """Список построчных сравнений по всем метрикам одного агрегата."""
    rows: list[MetricRow] = []
    for key, label, get_model, get_ref in _METRICS:
        m = get_model(res)
        r = get_ref(ref) if ref else None
        tol = tolerances.get(key, default_tol)
        if m is None or r is None:
            rows.append(
                MetricRow(
                    obj_id,
                    obj_name,
                    water,
                    res.aggregate_id,
                    res.pump_kind,
                    label,
                    _round(m),
                    _round(r),
                    None,
                    None,
                    tol,
                    NA,
                )
            )
            continue
        abs_dev = m - r
        rel_dev = abs_dev / abs(r) if r != 0 else None
        rows.append(
            MetricRow(
                obj_id,
                obj_name,
                water,
                res.aggregate_id,
                res.pump_kind,
                label,
                _round(m),
                _round(r),
                _round(abs_dev),
                _round(rel_dev, 4),
                tol,
                _status(rel_dev, tol),
            )
        )
    return rows


def compare_cell_bindings(
    cells: list[CellBinding],
    results: dict[str, AuditResult],
    tolerances: dict,
    default_tol: float = 0.05,
) -> list[CellRow]:
    """Сверить каждую reference-ячейку с моделью; input/passport оставить как trace."""
    rows: list[CellRow] = []
    for cell in cells:
        model = None
        abs_dev = None
        rel_dev = None
        tol = None
        status = "trace"
        if cell.role == "reference":
            tol = tolerances.get(cell.field, default_tol)
            res = results.get(cell.aggregate_id)
            get_model = _CELL_MODEL_BY_FIELD.get(cell.field)
            model = get_model(res) if res and get_model else None
            if model is None or cell.value is None:
                status = NA
            else:
                abs_dev = model - cell.value
                rel_dev = abs_dev / abs(cell.value) if cell.value != 0 else None
                status = _status(rel_dev, tol)
        rows.append(
            CellRow(
                object_id=cell.object_id,
                object_name=cell.object_name,
                water_type=cell.water_type,
                aggregate_id=cell.aggregate_id,
                role=cell.role,
                field=cell.field,
                label=cell.label,
                method_ref=cell.method_ref,
                unit=cell.unit,
                sheet=cell.sheet,
                label_cell=cell.label_cell,
                value_cell=cell.value_cell,
                raw=cell.raw,
                excel_value=_round(cell.value),
                model_value=_round(model),
                abs_dev=_round(abs_dev),
                rel_dev=_round(rel_dev, 4),
                tolerance=tol,
                status=status,
            )
        )
    return rows


def _round(x, nd: int = 3):
    return round(x, nd) if isinstance(x, (int, float)) else x


def row_to_dict(row: MetricRow) -> dict:
    return asdict(row)


def cell_row_to_dict(row: CellRow) -> dict:
    return asdict(row)
