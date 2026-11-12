"""Годовые выгрузки «Измерения» (xls) и их слияние с выгрузками ТИ."""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from ppd_audit import db_import
from ppd_audit.config import project_root
from ppd_audit.db_seed import bootstrap_database, seed_telemetry_from_scada
from ppd_audit.ingest.measurement_export import (
    ExportSheet,
    column_rule,
    export_files,
    read_exports,
)
from ppd_audit.ingest.scada_txt import ScadaMapping, ScadaPoint, ScadaTag


ROOT = project_root()
EXPORTS = ROOT / "data" / "telemetry" / "exports"
MAPPING = ScadaMapping.from_yaml(ROOT / "config" / "scada_tags.yaml")
needs_exports = pytest.mark.skipif(not export_files(EXPORTS), reason="нет годовой выгрузки")

TI_HEADER = "ТГ_НАИМЕНОВАНИЕ,КОН_ДАТА,ЗНАЧЕНИЕ_ИЗМЕРЕНИЯ"


@pytest.mark.parametrize(
    ("header", "code"),
    [
        (" Давление на выкиде", "POUNA"),
        (" Давление на приёме", "PINNA"),
        ("Давление в коллекторе", "PKOL_"),
        (" Расход на выкиде НА", "QVD__"),
        ("Расход на выкиде", "QVD__"),
        ("Акт.прямая мощность, кВт", "APWCN"),
        ("Мгновенный расход НА-1", None),
        (" Мгн расход на выкиде НА", None),
        ("Кач.", None),
    ],
)
def test_columns_map_to_model_tags(header, code):
    rule = column_rule(header)
    assert (rule.code if rule else None) == code


@needs_exports
def test_real_export_is_read_completely():
    sheets, skipped = read_exports(
        export_files(EXPORTS)[0], MAPPING.measurement_exports, MAPPING.interval_hours
    )

    assert skipped == []
    titles = {sheet.point_title for sheet in sheets}
    assert {"Аз КНС 54. НА 1", "Ек КНС 97ПР.НА 02", "Дж КНС ОПУ.Контр 1"} <= titles
    assert all(sheet.start == datetime(2025, 10, 25) for sheet in sheets)
    assert all(sheet.end == datetime(2026, 10, 25) for sheet in sheets)


@needs_exports
def test_power_becomes_interval_energy_and_totals_are_skipped():
    sheets, _ = read_exports(
        export_files(EXPORTS)[0], MAPPING.measurement_exports, MAPPING.interval_hours
    )
    energy = [
        point
        for sheet in sheets
        for point in sheet.points
        if point.tag == ScadaTag("5401", "PUMP_001", "APWCN", True)
    ]

    assert energy[0].timestamp == datetime(2025, 10, 25, 0, 30)
    assert energy[0].value == pytest.approx(869.04 * 0.5)
    assert all(point.value < 1000 for point in energy)  # нет строки «Итого:»


def _q_day(db) -> list[dict]:
    return [row for row in db.measurements("kns97pren", "НА-2 ПР") if row["metric"] == "q_day"]


def _ti_zip(path: Path, lines: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ТИ.txt", "\n".join([TI_HEADER, *lines]).encode("cp1251"))


def _fake_export(monkeypatch, points: list[ScadaPoint], start: datetime, end: datetime):
    sheet = ExportSheet("год.zip/НА.xls", "Ек КНС 97ПР.НА 02", start, end, points)
    monkeypatch.setattr(db_import, "export_files", lambda root: [Path("год.zip")])
    monkeypatch.setattr(db_import, "read_exports", lambda *args: ([sheet], []))


def test_export_replaces_ti_inside_its_period(tmp_path, monkeypatch):
    scada = tmp_path / "scada"
    scada.mkdir()
    _ti_zip(
        scada / "ЕН КНС-97ПР ТИ.zip",
        [
            "KNS__#0297#PUMP_#002#QVD__#I3,01.07.2026 0:30:00,10",
            "KNS__#0297#PUMP_#002#QVD__#I3,02.07.2026 0:30:00,99",
        ],
    )
    tag = ScadaTag("0297", "PUMP_002", "QVD__", True)
    _fake_export(
        monkeypatch,
        [
            ScadaPoint(tag, datetime(2026, 7, 2, 0, 30), 20),
            ScadaPoint(tag, datetime(2026, 7, 3, 0, 30), 30),
        ],
        datetime(2026, 7, 2),
        datetime(2026, 7, 4),
    )
    db = bootstrap_database(tmp_path / "audit.sqlite", ROOT / "config" / "plants")

    db_import.import_scada_exports(db, scada, MAPPING, tmp_path)

    rows = {row["timestamp"][:10]: (row["value"], row["source_file"]) for row in _q_day(db)}
    assert rows["2026-07-01"] == (10, "ЕН КНС-97ПР ТИ.zip")
    assert rows["2026-07-02"] == (20, "год.zip")  # не 99 из ТИ и не сумма
    assert rows["2026-07-03"][0] == 30


def test_new_export_triggers_full_rebuild(tmp_path, monkeypatch):
    scada = tmp_path / "scada"
    scada.mkdir()
    _ti_zip(scada / "ЕН КНС-97ПР ТИ.zip", ["KNS__#0297#PUMP_#002#QVD__#I3,01.07.2026 0:30:00,10"])
    tags = ROOT / "config" / "scada_tags.yaml"
    db = bootstrap_database(tmp_path / "audit.sqlite", ROOT / "config" / "plants")
    empty = tmp_path / "exports"
    empty.mkdir()

    first = seed_telemetry_from_scada(db, scada, tags, empty)
    again = seed_telemetry_from_scada(db, scada, tags, empty)
    tag = ScadaTag("0297", "PUMP_002", "QVD__", True)
    _fake_export(
        monkeypatch,
        [ScadaPoint(tag, datetime(2026, 7, 2, 0, 30), 20)],
        datetime(2026, 7, 2),
        datetime(2026, 7, 3),
    )
    monkeypatch.setattr(
        "ppd_audit.db_seed.scada_source_names",
        lambda root, exports: ["ЕН КНС-97ПР ТИ.zip", "год.zip"],
    )
    rebuilt = seed_telemetry_from_scada(db, scada, tags, empty)

    assert first.stored > 0 and again.stored == 0
    assert rebuilt.stored > 0
    days = [row["timestamp"][:10] for row in _q_day(db)]
    assert days == ["2026-07-01", "2026-07-02"]
