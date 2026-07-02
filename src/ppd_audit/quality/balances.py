"""Сведение балансов: объёмный (УУЖ ↔ перекачка), энергетический, УРЭ факт.

Каждый баланс даёт невязку и флаг — это часть прозрачности расчёта и основа
проверки точности УРЭ к учёту (ТЗ, критерий ≥80 %).
"""

from __future__ import annotations

import pandas as pd


def daily_flow_volume(flow: pd.DataFrame, max_gap_h: float = 1.0) -> pd.DataFrame:
    """Суточный объём по УУЖ из мгновенного расхода (м³/ч), м³/сут.

    Интеграл V = Σ Q_i · Δt_i (левый Риман). Δt — до следующего отсчёта;
    интервалы > max_gap_h обрезаются (пропуск телеметрии не раздувает объём).
    """
    if flow is None or flow.empty:
        return pd.DataFrame(columns=["date", "volume_uuj"])
    d = flow.dropna(subset=["value"]).sort_values("timestamp").reset_index(drop=True)
    dt_h = d["timestamp"].diff().shift(-1).dt.total_seconds() / 3600.0
    dt_h = dt_h.clip(upper=max_gap_h).fillna(0.0)
    d = d.assign(vol=d["value"] * dt_h, date=d["timestamp"].dt.normalize())
    out = d.groupby("date", as_index=False)["vol"].sum().rename(columns={"vol": "volume_uuj"})
    return out


def volume_balance(flow: pd.DataFrame, transfer: pd.DataFrame) -> dict:
    """Невязка объёмного баланса: УУЖ (интеграл расхода) ↔ перекачка (факт)."""
    uuj = daily_flow_volume(flow)
    if uuj.empty or transfer is None or transfer.empty:
        return {"note": "нет данных для баланса"}
    tr = transfer.copy()
    tr["date"] = pd.to_datetime(tr["date"]).dt.normalize()
    merged = uuj.merge(tr[["date", "fact"]], on="date", how="inner")
    if merged.empty:
        return {"note": "нет пересечения периодов УУЖ и перекачки",
                "uuj_period": [str(uuj.date.min()), str(uuj.date.max())],
                "transfer_period": [str(tr.date.min()), str(tr.date.max())]}
    merged["resid"] = merged["volume_uuj"] - merged["fact"]
    merged["resid_pct"] = merged["resid"] / merged["fact"] * 100.0
    return {
        "overlap_days": len(merged),
        "uuj_total": round(merged["volume_uuj"].sum(), 1),
        "fact_total": round(merged["fact"].sum(), 1),
        "residual_total": round(merged["resid"].sum(), 1),
        "residual_pct_median": round(merged["resid_pct"].median(), 1),
        "note": "положительная невязка → УУЖ показывает больше учёта (рециркуляция/простои)",
    }


def energy_summary(energy: dict[str, pd.DataFrame]) -> dict:
    """Суммарная энергия по агрегатам и доли (ожидаем доминирование рабочего Н-4)."""
    totals = {agg: round(float(df["kwh"].sum()), 1) for agg, df in energy.items() if df is not None}
    grand = sum(totals.values()) or 1.0
    shares = {agg: round(v / grand, 4) for agg, v in totals.items()}
    return {"totals_kwh": totals, "shares": shares, "grand_total_kwh": round(grand, 1)}


def sec_fact(energy: dict[str, pd.DataFrame], transfer: pd.DataFrame, flow: pd.DataFrame) -> dict:
    """УРЭ факт = Σ кВт·ч / объём (16) на пересекающемся периоде.

    Объём берётся двумя способами: по перекачке (учётный) и по УУЖ — для сопоставления.
    """
    if not energy or transfer is None or transfer.empty:
        return {"note": "нет данных"}
    # общий период энергии
    all_e = pd.concat([df.assign(agg=a) for a, df in energy.items() if df is not None])
    all_e["date"] = all_e["timestamp"].dt.normalize()
    e_start, e_end = all_e["date"].min(), all_e["date"].max()

    tr = transfer.copy()
    tr["date"] = pd.to_datetime(tr["date"]).dt.normalize()
    tr_overlap = tr[(tr["date"] >= e_start) & (tr["date"] <= e_end)]
    e_overlap = all_e[(all_e["date"] >= tr["date"].min()) & (all_e["date"] <= tr["date"].max())]

    energy_kwh = float(e_overlap["kwh"].sum())
    vol_transfer = float(tr_overlap["fact"].sum())
    uuj = daily_flow_volume(flow)
    uuj_overlap = uuj[(uuj["date"] >= e_start) & (uuj["date"] <= e_end)] if not uuj.empty else uuj
    vol_uuj = float(uuj_overlap["volume_uuj"].sum()) if not uuj_overlap.empty else 0.0

    res = {
        "overlap_period": [str(max(e_start, tr["date"].min())), str(min(e_end, tr["date"].max()))],
        "energy_kwh": round(energy_kwh, 1),
        "volume_transfer_m3": round(vol_transfer, 1),
        "volume_uuj_m3": round(vol_uuj, 1),
    }
    if vol_transfer > 0:
        res["sec_fact_by_transfer"] = round(energy_kwh / vol_transfer, 3)
    if vol_uuj > 0:
        res["sec_fact_by_uuj"] = round(energy_kwh / vol_uuj, 3)
    res["note"] = "УРЭ_факт по перекачке — приоритетный (ближе к учёту)"
    return res
