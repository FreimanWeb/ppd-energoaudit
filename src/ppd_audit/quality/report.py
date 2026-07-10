"""Сборка отчёта о качестве данных по нормализованному датасету."""

from __future__ import annotations

import json
from pathlib import Path

from ..config import project_root
from ..ingest.pipeline import NormalizedDataset
from . import balances, checks


def build_quality_report(ds: NormalizedDataset) -> dict:
    """Полный отчёт качества: ряды, журналы, пропуски, балансы."""
    rep: dict = {"plant_id": ds.plant_id, "series": {}, "journals": {}, "balances": {}}

    for agg, df in ds.pressure_in.items():
        rep["series"][f"p_in_{agg}"] = checks.series_quality(df)
    for agg, df in ds.pressure_out.items():
        rep["series"][f"p_out_{agg}"] = checks.series_quality(df)
    if ds.flow is not None:
        rep["series"]["flow"] = checks.series_quality(ds.flow)
    for key, df in ds.levels.items():
        rep["series"][key] = checks.series_quality(df)

    for agg, df in ds.journals.items():
        rep["journals"][agg] = checks.runtime_from_journal(df)

    if ds.transfer is not None:
        rep["transfer_gaps"] = checks.missing_calendar_dates(ds.transfer)

    rep["balances"]["volume"] = balances.volume_balance(ds.flow, ds.transfer)
    rep["balances"]["energy"] = balances.energy_summary(ds.energy)
    rep["balances"]["sec_fact"] = balances.sec_fact(ds.energy, ds.transfer, ds.flow)

    rep["flags"] = _derive_flags(rep)
    return rep


def _derive_flags(rep: dict) -> list[str]:
    """Человекочитаемые предупреждения по итогам проверок."""
    flags = []
    for name, q in rep["series"].items():
        if q.get("n", 0) == 0:
            flags.append(f"{name}: нет данных")
        elif q.get("zero_fraction", 0) > 0.5:
            flags.append(f"{name}: доля нулей {q['zero_fraction']:.0%} (вероятно резерв/простой)")
    vol = rep["balances"].get("volume", {})
    if isinstance(vol.get("residual_pct_median"), (int, float)) and abs(vol["residual_pct_median"]) > 10:
        flags.append(f"объёмный баланс: медианная невязка УУЖ↔перекачка {vol['residual_pct_median']}%")
    return flags


def save_quality_report(rep: dict, root: Path | None = None) -> Path:
    root = root or project_root()
    out = root / "data" / "generated" / rep["plant_id"]
    out.mkdir(parents=True, exist_ok=True)
    path = out / "quality_report.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    return path
