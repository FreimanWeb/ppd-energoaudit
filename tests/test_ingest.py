"""Интеграционные проверки слоя данных на реальной телеметрии ДНС-7с.

Кросс-валидация с React-прототипом: УРЭ_факт ≈ 1,244 кВт·ч/м³, доля Н-4 ≈ 85 %.
Тест пропускается, если исходные Excel недоступны (data/raw/...).
"""

import pytest

from ppd_audit.config import load_plant, project_root
from ppd_audit.ingest.pipeline import ingest_plant
from ppd_audit.quality.report import build_quality_report


@pytest.fixture(scope="module")
def report():
    plant = load_plant("dns7s")
    src = project_root() / plant.telemetry["source_file"]
    if not src.exists():
        pytest.skip(f"нет исходных данных: {src}")
    ds = ingest_plant("dns7s")
    return build_quality_report(ds)


def test_all_series_present(report):
    # 4 приёма + 4 выкида + расход + 2 уровня
    assert len(report["series"]) >= 11
    assert report["series"]["flow"]["n"] > 1000


def test_n4_dominates_energy(report):
    shares = report["balances"]["energy"]["shares"]
    assert shares["Н-4"] > 0.8, "основная энергия должна быть на рабочем Н-4 (~85%)"


def test_sec_fact_matches_prototype(report):
    sf = report["balances"]["sec_fact"]["sec_fact_by_transfer"]
    # прототип (TS) даёт 1,244 кВт·ч/м³ — допускаем небольшое расхождение
    assert sf == pytest.approx(1.244, abs=0.03)


def test_journal_dedup(report):
    j = report["journals"]["Н-4"]
    assert j["duplicates_removed"] > 0
    assert j["events_dedup"] < j["events_raw"]
