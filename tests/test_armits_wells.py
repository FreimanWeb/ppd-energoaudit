from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import pytest

from ppd_audit.ingest import armits_wells
from ppd_audit.ingest.armits_wells import MonthRecord, read_cards


ARCHIVE = Path(__file__).resolve().parents[1] / "data" / "network" / "armits_wells.zip"


def _month(
    volume: float | None, hours: float | None, month: date = date(2026, 9, 1)
) -> MonthRecord:
    return MonthRecord(month, None, None, None, None, None, None, None, volume, hours, None)


@pytest.mark.parametrize(
    ("value", "number"),
    [
        ("105.0", 105.0),
        ("  после 105.0", 105.0),
        ("12,5", 12.5),
        ("", None),
        ("атм", None),
        (0.0, 0.0),
    ],
)
def test_numbers_are_read_from_mixed_cells(value, number):
    assert armits_wells._number(value) == number


def test_month_labels_become_first_day_of_month():
    assert armits_wells._month("09.2026") == date(2026, 9, 1)
    assert armits_wells._month("мес,год") is None


def test_rate_while_working_and_calendar_mean_rate():
    record = _month(volume=720.0, hours=360.0)  # сентябрь — 30 суток

    assert record.rate_m3h == pytest.approx(2.0)
    assert record.mean_rate_m3h == pytest.approx(1.0)


def test_idle_month_has_no_rate():
    assert _month(volume=0.0, hours=0.0).rate_m3h is None
    assert _month(volume=None, hours=None).mean_rate_m3h is None


def test_cp866_names_from_windows_archives_are_decoded():
    info = zipfile.ZipInfo(
        "Выгрузка/54 Азнакаевскнефть/inf_skw2553.xls".encode("cp866").decode("cp437")
    )

    assert armits_wells._decoded(info) == "Выгрузка/54 Азнакаевскнефть/inf_skw2553.xls"


@pytest.mark.skipif(not ARCHIVE.exists(), reason="нет выгрузки АРМИТС")
@pytest.mark.parametrize("folder", ["54", "97-2", "ОПУ"])
def test_real_cards_have_history_and_pressures(folder):
    cards = read_cards(ARCHIVE, folder)

    assert len(cards) > 20
    assert all(card.months for card in cards)
    assert all(card.months == sorted(card.months, key=lambda r: r.month) for card in cards)
    assert any(card.p_after_choke_atm for card in cards)
    assert any(card.operating for card in cards)


@pytest.mark.skipif(not ARCHIVE.exists(), reason="нет выгрузки АРМИТС")
def test_agent_density_matches_station():
    cards = read_cards(ARCHIVE, "54")
    densities = [card.agent_density for card in cards if card.agent_density]

    assert max(set(densities), key=densities.count) == pytest.approx(1138.0)


@pytest.mark.skipif(not ARCHIVE.exists(), reason="нет выгрузки АРМИТС")
def test_history_holds_only_complete_months_before_the_current_one():
    for folder in ("54", "97-2", "ОПУ"):
        for card in read_cards(ARCHIVE, folder):
            assert card.current is not None
            assert all(record.month < card.current.month for record in card.months)
