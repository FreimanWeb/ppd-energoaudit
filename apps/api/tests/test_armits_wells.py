"""ARMIТС semantics tested without committing private source workbooks."""

from __future__ import annotations

import zipfile
from datetime import date
from types import SimpleNamespace

import pytest

from ppd_audit.config import project_root
from ppd_audit.ingest import armits_wells
from ppd_audit.ingest.armits_wells import MonthRecord, read_cards


class Sheet:
    def __init__(self, name, rows):
        self.name, self.rows = name, rows
        self.nrows = len(rows)
        self.ncols = max(map(len, rows))

    def row_values(self, row):
        return self.rows[row] + [""] * (self.ncols - len(self.rows[row]))

    def cell_value(self, row, column):
        return self.row_values(row)[column]


def workbook():
    current = [["ИHФОРМАЦИЯ ПО СКВАЖИHЕ 4623А ЦППД-9 на 14/10/2026г."]]
    current += [[""]] * 7
    current += [["Qжид.факт", 0, "м3/сут", "Ру до шт.", 130, "атм", " после  95,5"]]
    current += [["Qжид.предл.", 999, "м3/сут", "", "", "", ""]]
    monthly = [
        [""],
        ["Дата", "Фактический режим", *([""] * 8), "Отчетные данные"],
        [
            "мес,год",
            "Qжид.",
            "Qпред",
            "Qж.пред. уч.КНС",
            "Диам штуцера",
            "Р уст.",
            "Р бг.",
            "Р пл.",
            "Р заб.",
            "К прием.",
            "Жид-ть м3/сут ",
            "Закачка ",
            "Траб",
            "Тпрост",
            "Тогр",
            "Р уст.",
        ],
        [
            "",
            "м3/сут",
            "т/сут",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "м3/сут",
            "м3/мес",
            "ч/мес",
            "ч/мес",
            "ч/мес",
            "атм",
        ],
        ["10.2026", 100, 999, 999, 0, 90, 130, 180, 250, 0, 101, 3000, 700, 20, 24, 91],
    ]
    study = [
        [""],
        [
            "Гор",
            "Дата исследования",
            "Вид исслед.",
            "Р уст",
            "Рзаб/ Рпл.",
            "Т прост.",
            "Уро- вень",
            "Р затр",
            "Режим",
        ],
        ["", "", "", "", "", "", "", "", "Q реж", "Пл.агента", ""],
        ["", "", "", "атм", "атм", "ч", "м", "атм", "м3/сут", "г/см3", ""],
        [529, 45568, "Р заб ", 30, 216.1, "", 0, 0, 214.1, 1.138, ""],
        [529, 45575, "Р пл", 20, 191, "", 0, 0, 200, 1.142, ""],
        [529, 45580, "Н ст", 0, 0, "", 0, 0, 0, "", ""],
    ]
    sheets = {
        s.name: s
        for s in [Sheet("Режим", current), Sheet("Динамика", monthly), Sheet("ГДИ", study)]
    }
    return SimpleNamespace(sheet_by_name=sheets.__getitem__, datemode=0)


def read(tmp_path, monkeypatch, book):
    path = tmp_path / "input.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("export/54 Азнакаевскнефть/inf_skw4623.xls", b"private workbook")
    monkeypatch.setattr(armits_wells.xlrd, "open_workbook", lambda **kwargs: book)
    return armits_wells.read_armits_wells(path)


def test_preserves_identity_grain_zero_and_separates_reported_values(tmp_path, monkeypatch):
    records = read(tmp_path, monkeypatch, workbook())
    assert {r["well_code"] for r in records} == {"4623А"}
    assert {r["plant_code"] for r in records} == {"kns54an"}
    current = {r["metric"]: r for r in records if r["record_kind"] == "current"}
    assert current["flow_m3_day"]["value"] == 0
    assert current["p_well_after_choke"]["value"] == 95.5
    assert current["p_well_before_choke"]["unit"] == "атм"
    assert current["p_well_before_choke"]["observed_at"] == "2026-10-14"
    assert all(r["value"] != 999 for r in records)
    monthly = [r for r in records if r["grain"] == "month"]
    assert len(monthly) == 11
    assert {r["observed_at"] for r in monthly} == {"2026-10-01"}
    assert {r["record_kind"] for r in monthly} == {"monthly_actual", "monthly_reported"}
    assert all(r["source_row"] == 5 for r in monthly)


def test_study_pressure_depends_on_type_and_density_conversion(tmp_path, monkeypatch):
    records = read(tmp_path, monkeypatch, workbook())
    study = [r for r in records if r["record_kind"] == "study"]
    assert next(r for r in study if r["metric"] == "p_bottomhole")["value"] == 216.1
    assert next(r for r in study if r["metric"] == "p_reservoir")["study_type"] == "Р пл"
    assert next(r for r in study if r["metric"] == "p_study")["study_type"] == "Н ст"
    densities = [r for r in study if r["metric"] == "density_kgm3"]
    assert [(r["value"], r["unit"]) for r in densities] == [(1138.0, "кг/м³"), (1142.0, "кг/м³")]
    assert densities[0]["observed_at"] == "2024-10-03"


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), "bad"])
def test_rejects_invalid_numeric_values(tmp_path, monkeypatch, value):
    book = workbook()
    book.sheet_by_name("Режим").rows[8][1] = value
    with pytest.raises(ValueError, match="строка 9"):
        read(tmp_path, monkeypatch, book)


def test_rejects_unknown_headers(tmp_path, monkeypatch):
    book = workbook()
    book.sheet_by_name("Динамика").rows[2][6] = "unknown pressure"
    with pytest.raises(ValueError, match="заголовок"):
        read(tmp_path, monkeypatch, book)


def test_duplicate_month_rows_keep_provenance_and_blank_values_stay_missing(tmp_path, monkeypatch):
    book = workbook()
    monthly = book.sheet_by_name("Динамика")
    duplicate = list(monthly.rows[-1])
    duplicate[1] = ""
    monthly.rows.append(duplicate)
    monthly.nrows += 1
    records = read(tmp_path, monkeypatch, book)
    pressures = [
        r for r in records if r["metric"] == "p_well" and r["record_kind"] == "monthly_actual"
    ]
    assert [r["source_row"] for r in pressures] == [5, 6]
    assert (
        len([
            r
            for r in records
            if r["metric"] == "flow_m3_day" and r["record_kind"] == "monthly_actual"
        ])
        == 1
    )


def test_rejects_pressure_unit_change(tmp_path, monkeypatch):
    book = workbook()
    book.sheet_by_name("ГДИ").rows[3][3] = "МПа"
    with pytest.raises(ValueError, match="заголовок"):
        read(tmp_path, monkeypatch, book)


def test_rejects_empty_archive(tmp_path):
    path = tmp_path / "empty.zip"
    with zipfile.ZipFile(path, "w"):
        pass
    with pytest.raises(ValueError, match="ZIP"):
        armits_wells.read_armits_wells(path)


ARCHIVE = project_root() / "data" / "network" / "armits_wells.zip"


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
def test_history_holds_only_complete_months_before_the_current_one():
    for folder in ("54", "97-2", "ОПУ"):
        for card in read_cards(ARCHIVE, folder):
            assert card.current is not None
            assert all(record.month < card.current.month for record in card.months)
