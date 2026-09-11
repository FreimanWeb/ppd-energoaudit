from __future__ import annotations

from datetime import date, datetime

import pytest

from ppd_audit.ingest.downtime import (
    Downtime,
    DowntimeError,
    by_well,
    normalize_well,
    read_downtime,
    started_in,
)


openpyxl = pytest.importorskip("openpyxl")


HEADER = [
    "Цех", "В_в", "Скваж", "T_раб", "Причина_простоя", "Дата_непр_пр", "Q_ф",
]


def _book(tmp_path, rows: list[list], *, header: list[str] | None = None, title="КНС-97"):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append([title])
    sheet.append(header if header is not None else HEADER)
    for row in rows:
        sheet.append(row)
    path = tmp_path / "downtime.xlsx"
    workbook.save(path)
    return path


def test_normalize_well_drops_the_bore_suffix():
    assert normalize_well("3592Д/2") == "3592Д"
    assert normalize_well(" 2163Н ") == "2163Н"
    assert normalize_well("") == ""


def test_reads_wells_with_a_reason(tmp_path):
    path = _book(tmp_path, [
        ["8", "3", "2031", None, "Перестрел пласта", datetime(2026, 4, 1, 10, 55), 0],
        ["8", "3", "2161", 432, "Ожид.обвязки", datetime(2026, 6, 9, 12, 20), 10],
    ])
    records = read_downtime(path)

    assert [r.well for r in records] == ["2031", "2161"]
    assert records[0].reason == "Перестрел пласта"
    assert records[0].since == date(2026, 4, 1)
    assert records[1].runtime_hours == pytest.approx(432.0)


def test_wells_without_a_reason_are_skipped(tmp_path):
    path = _book(tmp_path, [
        ["8", "3", "2015", 744, "", None, 100],
        ["8", "3", "2031", None, "Перестрел пласта", datetime(2026, 4, 1), 0],
    ])
    assert [r.well for r in read_downtime(path)] == ["2031"]


def test_continuation_rows_without_a_well_are_skipped(tmp_path):
    """Под скважиной идут строки по пластам — номера скважины в них нет."""
    path = _book(tmp_path, [
        ["8", "3", "2031", None, "Перестрел пласта", datetime(2026, 4, 1), 0],
        [None, None, None, None, "Б1", None, None],
    ])
    assert len(read_downtime(path)) == 1


def test_bore_suffix_is_normalised_on_read(tmp_path):
    path = _book(tmp_path, [["8", "1", "3592Д/2", None, "Ремонт в/в", datetime(2026, 8, 6), 0]])

    assert read_downtime(path)[0].well == "3592Д"


def test_text_dates_are_accepted(tmp_path):
    path = _book(tmp_path, [["8", "1", "2031", None, "Ремонт", "09.06.2026 12:20", 0]])

    assert read_downtime(path)[0].since == date(2026, 6, 9)


def test_unreadable_date_becomes_none_not_an_error(tmp_path):
    path = _book(tmp_path, [["8", "1", "2031", None, "Ремонт", "когда-то", 0]])

    assert read_downtime(path)[0].since is None


def test_missing_file_gives_no_records(tmp_path):
    assert read_downtime(tmp_path / "нет.xlsx") == []


def test_file_without_the_expected_header_is_reported(tmp_path):
    path = _book(tmp_path, [["a", "b"]], header=["Цех", "Что-то"])

    with pytest.raises(DowntimeError):
        read_downtime(path)


def test_column_order_is_taken_from_the_header(tmp_path):
    """Столбцы ищутся по названию: перестановка в отчёте не должна ломать чтение."""
    path = _book(
        tmp_path,
        [["Перестрел пласта", "2031", datetime(2026, 4, 1)]],
        header=["Причина_простоя", "Скваж", "Дата_непр_пр"],
    )
    record = read_downtime(path)[0]

    assert record.well == "2031"
    assert record.reason == "Перестрел пласта"
    assert record.since == date(2026, 4, 1)


def test_by_well_is_keyed_by_number():
    records = [Downtime("2031", "Ремонт"), Downtime("2161", "Ожид.обвязки")]

    assert set(by_well(records)) == {"2031", "2161"}


def test_started_in_keeps_only_the_window_and_sorts_by_date():
    records = [
        Downtime("2163Н", "Консервация", date(2023, 6, 9)),
        Downtime("2161", "Ожид.обвязки", date(2026, 6, 9)),
        Downtime("2031", "Перестрел пласта", date(2026, 4, 1)),
        Downtime("2077", "Исследование", None),
    ]
    selected = started_in(records, date(2026, 4, 1), date(2026, 7, 31))

    assert [r.well for r in selected] == ["2031", "2161"]


def test_started_in_includes_both_edges():
    records = [
        Downtime("a", "x", date(2026, 4, 1)),
        Downtime("b", "x", date(2026, 7, 31)),
    ]
    assert len(started_in(records, date(2026, 4, 1), date(2026, 7, 31))) == 2
