"""Пайплайн ingest: исходные Excel → нормализованные ряды на диске.

Читает все сигналы объекта по карте telemetry из паспорта (config/plants/<id>.yaml),
приводит к единому виду [timestamp, value, ...] и сохраняет в data/generated/<id>/.
Формат — CSV (без внешних зависимостей вроде pyarrow).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..config import load_plant, project_root
from ..models import Plant
from . import readers


@dataclass
class NormalizedDataset:
    """Нормализованные ряды объекта (в памяти)."""
    plant_id: str
    pressure_in: dict[str, pd.DataFrame] = field(default_factory=dict)   # agg → [ts, value]
    pressure_out: dict[str, pd.DataFrame] = field(default_factory=dict)
    flow: pd.DataFrame | None = None
    levels: dict[str, pd.DataFrame] = field(default_factory=dict)
    journals: dict[str, pd.DataFrame] = field(default_factory=dict)      # agg → [ts, state]
    energy: dict[str, pd.DataFrame] = field(default_factory=dict)        # agg → [ts, kwh, quality]
    transfer: pd.DataFrame | None = None                                 # [date, plan, fact, counter]


def _sheet_for(prefix: str, agg: str) -> str:
    """'Давление на приеме' + 'Н-4' → 'Давление на приеме Н-4'."""
    return f"{prefix} {agg}"


def ingest_plant(plant_id: str = "dns7s", root: Path | None = None) -> NormalizedDataset:
    """Прочитать и нормализовать всю телеметрию объекта."""
    root = root or project_root()
    plant: Plant = load_plant(plant_id)
    tlm = plant.telemetry or {}
    src = root / tlm["source_file"]
    trf = root / tlm["transfer_file"]
    sig = tlm["signals"]
    aggs = tlm.get("aggregates_with_series", [])

    ds = NormalizedDataset(plant_id=plant_id)

    for agg in aggs:
        ds.pressure_in[agg] = readers.read_timeseries(src, _sheet_for(sig["p_in"]["sheet_prefix"], agg))
        ds.pressure_out[agg] = readers.read_timeseries(src, _sheet_for(sig["p_out"]["sheet_prefix"], agg))
        ds.journals[agg] = readers.read_journal(src, _sheet_for(sig["state"]["sheet_prefix"], agg))
        ds.energy[agg] = readers.read_energy(src, _sheet_for(sig["energy"]["sheet_prefix"], agg))

    ds.flow = readers.read_timeseries(src, sig["flow"]["sheet"])
    for key in ("level_be1", "level_be2"):
        if key in sig:
            ds.levels[key] = readers.read_timeseries(src, sig[key]["sheet"])

    ds.transfer = readers.read_transfer(trf)
    return ds


# --- Сохранение -----------------------------------------------------------

def _save_df(df: pd.DataFrame, path_no_ext: Path) -> Path:
    p = path_no_ext.with_suffix(".csv")
    df.to_csv(p, index=False)
    return p


def save_dataset(ds: NormalizedDataset, root: Path | None = None) -> Path:
    """Сохранить нормализованные ряды в data/generated/<plant_id>/."""
    root = root or project_root()
    out = root / "data" / "generated" / ds.plant_id / "series"
    out.mkdir(parents=True, exist_ok=True)
    for agg, df in ds.pressure_in.items():
        _save_df(df, out / f"p_in_{agg}")
    for agg, df in ds.pressure_out.items():
        _save_df(df, out / f"p_out_{agg}")
    for agg, df in ds.journals.items():
        _save_df(df, out / f"state_{agg}")
    for agg, df in ds.energy.items():
        _save_df(df, out / f"energy_{agg}")
    for key, df in ds.levels.items():
        _save_df(df, out / key)
    if ds.flow is not None:
        _save_df(ds.flow, out / "flow")
    if ds.transfer is not None:
        _save_df(ds.transfer, out / "transfer")
    return out
