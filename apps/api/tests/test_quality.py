"""Негативные тесты самопроверок слоя качества данных (аудит ядра 02.07.2026):
балансы должны РЕАЛЬНО срабатывать на рассогласованных данных, а не только
проходить на чистых.
"""

import pandas as pd
import pytest

from ppd_audit.quality.balances import daily_flow_volume, volume_balance


def _flow_series(hours: int, q_m3h: float, start="2026-01-01") -> pd.DataFrame:
    ts = pd.date_range(start, periods=hours, freq="h")
    return pd.DataFrame({"timestamp": ts, "value": [q_m3h] * hours})


def test_daily_flow_volume_integrates():
    # 24 ч × 100 м³/ч → 2400 м³ за первые сутки (последний отсчёт без Δt)
    flow = _flow_series(25, 100.0)
    vol = daily_flow_volume(flow)
    first = vol[vol["date"] == pd.Timestamp("2026-01-01")]["volume_uuj"].iloc[0]
    assert first == pytest.approx(2400.0, rel=1e-9)


def test_volume_balance_detects_gap():
    """УУЖ показывает 2400 м³/сут, перекачка — 3000 → невязка −20 % ловится."""
    flow = _flow_series(24 * 3 + 1, 100.0)
    transfer = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=3, freq="D"),
        "fact": [3000.0, 3000.0, 3000.0],
    })
    res = volume_balance(flow, transfer)
    assert res["overlap_days"] == 3
    assert res["residual_pct_median"] == pytest.approx(-20.0, abs=0.5)


def test_volume_balance_clean_data_ok():
    """На согласованных данных невязка ≈ 0 (позитивный контроль негативного теста)."""
    flow = _flow_series(24 * 2 + 1, 100.0)
    transfer = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=2, freq="D"),
        "fact": [2400.0, 2400.0],
    })
    res = volume_balance(flow, transfer)
    assert abs(res["residual_pct_median"]) < 1.0


def test_volume_balance_no_overlap_is_flagged():
    """Непересекающиеся периоды — явное сообщение, а не тихий ноль."""
    flow = _flow_series(24, 100.0, start="2026-01-01")
    transfer = pd.DataFrame({"date": [pd.Timestamp("2026-03-01")], "fact": [2400.0]})
    res = volume_balance(flow, transfer)
    assert "нет пересечения" in res["note"]
