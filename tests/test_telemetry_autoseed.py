from __future__ import annotations

from datetime import datetime

import pytest

from ppd_audit.db import AuditDatabase
from ppd_audit.db_import import excel_telemetry_files
from ppd_audit.db_seed import seed_telemetry_from_excel, telemetry_is_example_only


def _database(tmp_path) -> AuditDatabase:
    database = AuditDatabase(tmp_path / "audit.sqlite")
    database.migrate()
    database.upsert_plant("kns54an", "КНС-54", "Азнакаевскнефть", "агрессивная", "кнс")
    database.upsert_aggregate("kns54an", "НА-1", "работа")
    return database


def test_has_measurements_reflects_content(tmp_path):
    database = _database(tmp_path)
    assert database.has_measurements() is False
    database.add_measurement(
        "kns54an", "НА-1", datetime(2026, 1, 1), "q_day", 2400.0, "м³/сут"
    )
    assert database.has_measurements() is True


def test_missing_directory_is_reported_not_raised(tmp_path):
    result = seed_telemetry_from_excel(_database(tmp_path), tmp_path / "нет-такого")
    assert result.files_found == 0
    assert result.imported is False
    assert result.reason == "каталог не найден"


def test_empty_directory_is_reported(tmp_path):
    empty = tmp_path / "telemetry"
    empty.mkdir()
    (empty / "README.md").write_text("не Excel", encoding="utf-8")
    result = seed_telemetry_from_excel(_database(tmp_path), empty)
    assert result.files_found == 0
    assert result.reason == "нет Excel-файлов"


def test_import_is_skipped_when_database_already_has_telemetry(tmp_path):
    database = _database(tmp_path)
    database.add_measurement(
        "kns54an", "НА-1", datetime(2026, 1, 1), "q_day", 2400.0, "м³/сут"
    )
    directory = tmp_path / "telemetry"
    directory.mkdir()
    (directory / "КНС-54 НА-1.xlsx").write_bytes(b"not really excel")

    result = seed_telemetry_from_excel(database, directory)

    assert result.files_found == 1
    assert result.imported is False
    assert result.reason == "телеметрия уже загружена"


def test_excel_files_are_found_recursively_without_temp_files(tmp_path):
    root = tmp_path / "telemetry"
    (root / "агрессивная вода").mkdir(parents=True)
    (root / "КНС-54 НА-1.xlsx").write_bytes(b"")
    (root / "агрессивная вода" / "КНС-ОПУ НА-2.xls").write_bytes(b"")
    (root / "~$КНС-54 НА-1.xlsx").write_bytes(b"")
    (root / "README.md").write_text("", encoding="utf-8")

    flat = excel_telemetry_files(root)
    deep = excel_telemetry_files(root, recursive=True)

    assert [p.name for p in flat] == ["КНС-54 НА-1.xlsx"]
    assert {p.name for p in deep} == {"КНС-54 НА-1.xlsx", "КНС-ОПУ НА-2.xls"}


def test_unreadable_excel_is_named_not_swallowed(tmp_path):
    directory = tmp_path / "telemetry"
    directory.mkdir()
    (directory / "КНС-54 НА-1.xlsx").write_bytes(b"not really excel")

    result = seed_telemetry_from_excel(_database(tmp_path), directory)

    assert result.unreadable == ("КНС-54 НА-1.xlsx",)
    assert result.imported is False


def test_one_broken_file_does_not_block_the_others(tmp_path):
    directory = tmp_path / "telemetry"
    directory.mkdir()
    (directory / "КНС-54 НА-1.xlsx").write_bytes(b"not really excel")
    _write_minimal_xlsx(directory / "КНС-54 НА-2.xlsx")

    result = seed_telemetry_from_excel(_database(tmp_path), directory)

    assert result.files_found == 2
    assert result.unreadable == ("КНС-54 НА-1.xlsx",)


def test_example_files_are_flagged_as_demo(tmp_path):
    database = _database(tmp_path)
    database.add_measurement(
        "kns54an",
        "НА-1",
        datetime(2026, 1, 1),
        "q_day",
        2400.0,
        "м³/сут",
        source_file="ПРИМЕР КНС-54 НА-1.xlsx",
    )
    assert telemetry_is_example_only(database) is True

    database.add_measurement(
        "kns54an",
        "НА-1",
        datetime(2026, 1, 2),
        "q_day",
        2500.0,
        "м³/сут",
        source_file="КНС-54 НА-1 выгрузка.xlsx",
    )
    assert telemetry_is_example_only(database) is False


def test_empty_database_is_not_called_demo(tmp_path):
    assert telemetry_is_example_only(_database(tmp_path)) is False


def test_examples_can_be_excluded_from_import(tmp_path):
    directory = tmp_path / "telemetry"
    directory.mkdir()
    (directory / "ПРИМЕР КНС-54 НА-1.xlsx").write_bytes(b"not really excel")

    result = seed_telemetry_from_excel(
        _database(tmp_path), directory, include_examples=False
    )

    assert result.files_found == 0
    assert result.reason == "нет Excel-файлов"
    assert result.unreadable == ()


def _write_minimal_xlsx(path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Дата", "Значение"])
    sheet.append(["01.01.2026", 1.0])
    book.save(path)
