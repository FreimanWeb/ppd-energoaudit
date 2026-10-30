"""Контроль качества рядов: статистика, дедуп журналов, пропуски, флаги.

Дефекты исходников ДНС-7с (по «Контракт телеметрии»): дубли в журналах,
пропуски дат перекачки, большая доля нулей у резервных насосов.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def series_quality(df: pd.DataFrame, value_col: str = "value") -> dict:
    """Сводка качества временного ряда [timestamp, value]."""
    n = len(df)
    if n == 0:
        return {"n": 0, "note": "нет данных"}
    vals = df[value_col]
    ts = df["timestamp"]
    n_nan = int(vals.isna().sum())
    n_zero = int((vals == 0).sum())
    n_dup_ts = int(ts.duplicated().sum())
    return {
        "n": n,
        "period": [str(ts.min()), str(ts.max())],
        "n_nan": n_nan,
        "n_zero": n_zero,
        "zero_fraction": round(n_zero / n, 4),
        "dup_timestamps": n_dup_ts,
        "value_min": _r(vals.min()),
        "value_median": _r(vals.median()),
        "value_max": _r(vals.max()),
    }


def dedup_journal(df: pd.DataFrame) -> pd.DataFrame:
    """Свернуть журнал состояний к переходам: убрать подряд идущие одинаковые состояния.

    Возвращает [timestamp, state] только в точках смены состояния.
    """
    if df.empty:
        return df
    d = df.sort_values("timestamp").reset_index(drop=True)
    keep = d["state"] != d["state"].shift(1)
    return d[keep].reset_index(drop=True)


def runtime_from_journal(df: pd.DataFrame) -> dict:
    """Наработка агрегата по журналу: сумма интервалов ВКЛ→ОТКЛ."""
    d = dedup_journal(df)
    if d.empty:
        return {"events_raw": len(df), "events_dedup": 0, "runtime_hours": 0.0, "starts": 0}
    runtime = pd.Timedelta(0)
    on_ts = None
    starts = 0
    for _, row in d.iterrows():
        if row["state"] == "ВКЛ":
            on_ts = row["timestamp"]
            starts += 1
        elif row["state"] == "ОТКЛ" and on_ts is not None:
            runtime += row["timestamp"] - on_ts
            on_ts = None
    return {
        "events_raw": len(df),
        "events_dedup": len(d),
        "duplicates_removed": len(df) - len(d),
        "runtime_hours": round(runtime.total_seconds() / 3600.0, 1),
        "starts": starts,
    }


def missing_calendar_dates(df: pd.DataFrame, date_col: str = "date") -> dict:
    """Пропущенные календарные даты в суточном ряду (перекачка)."""
    if df.empty:
        return {"n": 0, "missing_dates": 0}
    dates = pd.to_datetime(df[date_col]).dt.normalize().drop_duplicates().sort_values()
    full = pd.date_range(dates.min(), dates.max(), freq="D")
    missing = full.difference(dates)
    return {
        "n": len(dates),
        "span_days": len(full),
        "missing_dates": len(missing),
        "missing_fraction": round(len(missing) / len(full), 4),
    }


def _r(x, nd=3):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return round(float(x), nd)
