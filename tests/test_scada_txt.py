"""Разбор выгрузок АСУ ТП (ingest/scada_txt.py).

Проверяется то, на чём такие выгрузки обычно и ломаются: cp1251, запятая
одновременно как разделитель полей и десятичный разделитель, свод накоплений
за интервал в сутки и отличие тега-счётчика от тега-расхода.
"""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from ppd_audit.ingest.scada_txt import (
    ScadaFormatError,
    ScadaMapping,
    build_rows,
    iter_points,
    parse_decimal,
    parse_tag,
    parse_timestamp,
    read_rows,
    scada_files,
)


TI_HEADER = "ТГ_НАИМЕНОВАНИЕ,КОН_ДАТА,ЗНАЧЕНИЕ_ИЗМЕРЕНИЯ"
TS_HEADER = (
    "ТГ_НАИМЕНОВАНИЕ,ПРИЗНАК_СОБЫТИЯ,ИСТОЧНИК_СОБЫТИЯ,ЗНАЧЕНИЕ_СИГНАЛА,"
    "КОН_ДАТА,ТЕКСТ_СОБЫТИЯ,ИСТОЧНИК"
)

MAPPING_YAML = """
schema: scada_tags.v1
interval_hours: 0.5
objects:
  "0197":
    plant: kns97pren
    technical_place: main
    aggregates:
      PUMP_003: "НА-3"
points:
  PINNA: {metric: p_in, unit: МПа}
  POUNA: {metric: p_out, unit: МПа}
  S_KWT: {metric: power, unit: кВт}
station_points:
  PKOL_: {metric: p_bg, unit: МПа}
interval_sums:
  QVD__: {metric: q_day, unit: м³/сут, integral: true}
  APWCN:
    metric: energy
    unit: кВт·ч
    integral: true
    runtime_source: true
    derive_power: {metric: power, unit: кВт}
runtime:
  metric: runtime
  unit: ч
states:
  NAON_: {metric: pump_state}
"""


@pytest.fixture
def mapping(tmp_path) -> ScadaMapping:
    path = tmp_path / "scada_tags.yaml"
    path.write_text(MAPPING_YAML, encoding="utf-8")
    return ScadaMapping.from_yaml(path)


def _ti(lines: list[str]) -> list:
    return list(iter_points(iter([TI_HEADER, *lines])))


# ───────────────────────── разбор строк ─────────────────────────


def test_parse_tag_reads_object_unit_and_integral_flag():
    tag = parse_tag("KNS__#0197#PUMP_#003#APWCN#I3")
    assert (tag.object_code, tag.unit, tag.code, tag.integral) == (
        "0197",
        "PUMP_003",
        "APWCN",
        True,
    )
    assert parse_tag("KNS__#0197#PUMP_#003#APWCN").integral is False
    assert parse_tag("мусор") is None


def test_parse_timestamp_accepts_all_three_forms():
    assert parse_timestamp("01.07.2025") == datetime(2025, 7, 1)
    assert parse_timestamp("01.07.2025 0:30:00") == datetime(2025, 7, 1, 0, 30)
    assert parse_timestamp("01.07.2025 12:05") == datetime(2025, 7, 1, 12, 5)
    assert parse_timestamp("2025-07-01") is None


def test_decimal_comma_is_reassembled():
    """«176,64» приходит двумя полями, потому что запятая — и разделитель полей."""
    assert parse_decimal(["176", "64"]) == pytest.approx(176.64)
    assert parse_decimal(["0"]) == 0.0
    assert parse_decimal([""]) is None
    assert parse_decimal(["не число"]) is None


def test_measurement_line_with_decimal_comma():
    points = _ti(["KNS__#0197#PUMP_#003#APWCN#I3,01.07.2025 0:30:00,176,64"])
    assert len(points) == 1
    assert points[0].value == pytest.approx(176.64)
    assert points[0].timestamp == datetime(2025, 7, 1, 0, 30)


def test_signal_line_reads_value_and_date_by_position():
    """В ТС текст события содержит запятые — поля берутся слева по позициям."""
    line = (
        "KNS__#0197#PUMP_#003#NAON_,НОРМ,ТС,1,01.07.2025 10:29:31,"
        "Работа,Ек КНС 97,Контр 01, Состояние НА"
    )
    points = list(iter_points(iter([TS_HEADER, line])))
    assert len(points) == 1
    assert points[0].value == 1.0
    assert points[0].timestamp == datetime(2025, 7, 1, 10, 29, 31)


def test_unknown_header_is_rejected():
    with pytest.raises(ScadaFormatError):
        list(iter_points(iter(["что-то своё,колонка"])))


# ───────────────────────── свод в canonical ─────────────────────────


def _energy_day(mapping: ScadaMapping, values: list[tuple[str, str]]):
    lines = [f"KNS__#0197#PUMP_#003#APWCN#I3,{ts},{value}" for ts, value in values]
    return build_rows(iter(_ti(lines)), mapping)


def test_interval_sums_become_one_daily_row(mapping):
    rows = _energy_day(
        mapping,
        [("01.07.2025", "100"), ("01.07.2025 0:30:00", "50"), ("02.07.2025", "70")],
    )
    energy = [r for r in rows if r.metric == "energy"]
    assert len(energy) == 2
    first = next(r for r in energy if r.timestamp == datetime(2025, 7, 1))
    assert first.value == pytest.approx(150.0)
    assert first.unit == "кВт·ч"
    assert first.aggregate_code == "НА-3"


def test_counter_tag_without_integral_suffix_is_ignored(mapping):
    """APWCN без #I3 — счётчик с начала эксплуатации, его суммировать нельзя."""
    lines = [
        "KNS__#0197#PUMP_#003#APWCN,01.07.2025,518745",
        "KNS__#0197#PUMP_#003#APWCN#I3,01.07.2025,100",
    ]
    rows = build_rows(iter(_ti(lines)), mapping)
    energy = [r for r in rows if r.metric == "energy"]
    assert len(energy) == 1
    assert energy[0].value == pytest.approx(100.0)


def test_runtime_counts_intervals_with_energy(mapping):
    lines = [
        "KNS__#0197#PUMP_#003#APWCN#I3,01.07.2025,10",
        "KNS__#0197#PUMP_#003#APWCN#I3,01.07.2025 0:30:00,12",
        "KNS__#0197#PUMP_#003#APWCN#I3,01.07.2025 1:00:00,0",
        "KNS__#0197#PUMP_#003#QVD__#I3,01.07.2025,22",
    ]
    rows = build_rows(iter(_ti(lines)), mapping)
    runtime = next(r for r in rows if r.metric == "runtime")
    assert runtime.value == pytest.approx(1.0)  # два интервала по 0,5 ч
    q_day = next(r for r in rows if r.metric == "q_day")
    assert q_day.value == pytest.approx(22.0)


def test_runtime_never_exceeds_the_day(mapping):
    lines = [
        f"KNS__#0197#PUMP_#003#APWCN#I3,01.07.2025 {h}:{m:02d}:00,5"
        for h in range(24)
        for m in (0, 15, 30, 45)
    ]
    rows = build_rows(iter(_ti(lines)), mapping)
    runtime = next(r for r in rows if r.metric == "runtime")
    assert runtime.value == 24.0


def test_power_is_derived_from_interval_energy(mapping):
    """P = W/T (формула 12): 176,64 кВт·ч за полчаса — это 353,28 кВт."""
    rows = _energy_day(mapping, [("01.07.2025 0:30:00", "176,64")])
    power = next(r for r in rows if r.metric == "power")
    assert power.value == pytest.approx(353.28)
    assert power.unit == "кВт"
    assert power.timestamp == datetime(2025, 7, 1, 0, 30)


def test_direct_power_sensor_wins_over_derived(mapping):
    """Там, где есть свой датчик мощности, выводить её из энергии не нужно."""
    lines = [
        "KNS__#0197#PUMP_#003#S_KWT,01.07.2025 0:30:00,300",
        "KNS__#0197#PUMP_#003#APWCN#I3,01.07.2025 0:30:00,176,64",
    ]
    rows = build_rows(iter(_ti(lines)), mapping)
    power = [r for r in rows if r.metric == "power"]
    assert [r.value for r in power] == [300.0]


def test_step_signal_stores_only_changes(mapping):
    lines = [
        "KNS__#0197#PUMP_#003#PINNA,01.07.2025 0:00:00,1,5",
        "KNS__#0197#PUMP_#003#PINNA,01.07.2025 0:02:00,1,5",
        "KNS__#0197#PUMP_#003#PINNA,01.07.2025 0:04:00,1,5",
        "KNS__#0197#PUMP_#003#PINNA,01.07.2025 0:06:00,1,7",
    ]
    rows = build_rows(iter(_ti(lines)), mapping)
    p_in = [r for r in rows if r.metric == "p_in"]
    assert [r.value for r in p_in] == [1.5, 1.7]


def test_station_tag_has_no_aggregate(mapping):
    rows = build_rows(iter(_ti(["KNS__#0197#BG___#001#PKOL_,01.07.2025 0:00:00,9,2"])), mapping)
    p_bg = next(r for r in rows if r.metric == "p_bg")
    assert p_bg.aggregate_code is None
    assert p_bg.value == pytest.approx(9.2)


def test_unknown_object_and_unit_are_skipped(mapping):
    lines = [
        "KNS__#0999#PUMP_#003#APWCN#I3,01.07.2025,100",  # чужой объект
        "KNS__#0197#PUMP_#009#APWCN#I3,01.07.2025,100",  # агрегата нет в карте
    ]
    assert build_rows(iter(_ti(lines)), mapping) == []


def test_pump_state_from_signals(mapping, tmp_path):
    path = tmp_path / "ТС.txt"
    path.write_text(
        TS_HEADER
        + "\nKNS__#0197#PUMP_#003#NAON_,НОРМ,ТС,1,01.07.2025 10:29:31,Работа,Ек,Контр\n",
        encoding="cp1251",
    )
    rows = read_rows(path, mapping)
    state = next(r for r in rows if r.metric == "pump_state")
    assert state.value == 1.0
    assert state.aggregate_code == "НА-3"


# ───────────────────────── файлы и архивы ─────────────────────────


def test_reads_txt_in_cp1251(tmp_path, mapping):
    path = tmp_path / "ТИ.txt"
    path.write_text(
        TI_HEADER + "\nKNS__#0197#PUMP_#003#APWCN#I3,01.07.2025,100\n", encoding="cp1251"
    )
    rows = read_rows(path, mapping)
    assert any(r.metric == "energy" and r.value == 100.0 for r in rows)


def test_reads_txt_inside_zip(tmp_path, mapping):
    archive = tmp_path / "ЕН КНС-97 ТИ.zip"
    payload = (TI_HEADER + "\nKNS__#0197#PUMP_#003#APWCN#I3,01.07.2025,100\n").encode("cp1251")
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("ЕН КНС-97 ТИ.txt", payload)
    rows = read_rows(archive, mapping)
    assert any(r.metric == "energy" and r.value == 100.0 for r in rows)


def test_scada_files_finds_archives_recursively_without_temp(tmp_path):
    (tmp_path / "вложенная").mkdir()
    (tmp_path / "ЕН КНС-97 ТИ.zip").write_bytes(b"")
    (tmp_path / "вложенная" / "ЕН КНС-97 ТС.txt").write_text("", encoding="cp1251")
    (tmp_path / "~$черновик.zip").write_bytes(b"")
    (tmp_path / "README.md").write_text("", encoding="utf-8")

    names = {p.name for p in scada_files(tmp_path)}
    assert names == {"ЕН КНС-97 ТИ.zip", "ЕН КНС-97 ТС.txt"}


def test_scada_files_on_missing_directory(tmp_path):
    assert scada_files(tmp_path / "нет-такого") == []


def test_mapping_defaults_when_config_is_minimal(tmp_path):
    path = tmp_path / "m.yaml"
    path.write_text("schema: scada_tags.v1\n", encoding="utf-8")
    mapping = ScadaMapping.from_yaml(path)
    assert mapping.interval_hours == 0.5
    assert mapping.objects == {}
    assert build_rows(iter(_ti(["KNS__#0197#PUMP_#003#APWCN#I3,01.07.2025,1"])), mapping) == []


def test_real_export_shape_is_covered_by_fixture(tmp_path, mapping):
    """Строка ровно из присланной выгрузки проходит весь путь до canonical."""
    path = Path(tmp_path / "ТИ.txt")
    path.write_text(
        TI_HEADER
        + "\nKNS__#0197#PUMP_#003#QVD__#I3,01.07.2025,21,73"
        + "\nKNS__#0197#PUMP_#003#APWCN#I3,01.07.2025,177,12\n",
        encoding="cp1251",
    )
    rows = read_rows(path, mapping)
    by_metric = {r.metric: r.value for r in rows}
    assert by_metric["q_day"] == pytest.approx(21.73)
    assert by_metric["energy"] == pytest.approx(177.12)
    assert by_metric["power"] == pytest.approx(354.24)
    assert by_metric["runtime"] == pytest.approx(0.5)


# ───────────────────────── оборвавшиеся последние сутки ─────────────────────────


def _interval_lines(day: str, last_hhmm: str, aggregate: str = "PUMP_#003") -> list[str]:
    lines = []
    hour, minute = (int(part) for part in last_hhmm.split(":"))
    slot = 0
    while slot <= hour * 60 + minute:
        h, m = divmod(slot, 60)
        stamp = f"{day} {h}:{m:02d}:00"
        lines.append(f"KNS__#0197#{aggregate}#QVD__#I3,{stamp},10")
        lines.append(f"KNS__#0197#{aggregate}#APWCN#I3,{stamp},50")
        slot += 30
    return lines


def test_full_last_day_keeps_daily_totals(mapping):
    rows = build_rows(iter(_ti(_interval_lines("01.07.2025", "23:30"))), mapping)
    assert any(r.metric == "q_day" for r in rows)
    assert any(r.metric == "runtime" and r.value == 24.0 for r in rows)


def test_truncated_last_day_has_no_daily_totals(mapping):
    """Выгрузка обрывается в 11:30 — суточные итоги за этот день не пишутся."""
    lines = _interval_lines("01.07.2025", "23:30") + _interval_lines("02.07.2025", "11:30")
    rows = build_rows(iter(_ti(lines)), mapping)
    cut = datetime(2025, 7, 2).date()

    daily_metrics = [
        r.metric for r in rows
        if r.timestamp.date() == cut and r.metric in ("q_day", "energy", "runtime")
    ]
    assert daily_metrics == []
    # мгновенные значения при этом не теряются
    assert any(r.metric == "power" for r in rows)
    assert any(r.metric == "q_day" and r.timestamp.date() != cut for r in rows)


def test_only_the_last_day_is_dropped(mapping):
    """Полные предыдущие сутки сохраняются, обрывается только последний день."""
    lines = _interval_lines("01.07.2025", "23:30") + _interval_lines("02.07.2025", "11:30")
    rows = build_rows(iter(_ti(lines)), mapping)
    days = {r.timestamp.date() for r in rows if r.metric == "q_day"}
    assert days == {datetime(2025, 7, 1).date()}


def test_short_export_without_full_days_keeps_its_totals(mapping):
    """Выгрузили несколько часов — это и есть заказанное окно, итоги остаются."""
    rows = build_rows(iter(_ti(_interval_lines("01.07.2025", "03:30"))), mapping)
    assert any(r.metric == "q_day" for r in rows)


def test_gap_inside_the_period_is_not_a_truncation(mapping):
    """Пропуск интервалов в середине суток — не обрыв: значение держится дальше."""
    lines = [
        line
        for line in _interval_lines("01.07.2025", "23:30")
        if " 5:" not in line and " 6:" not in line
    ]
    rows = build_rows(iter(_ti(lines)), mapping)
    assert any(r.metric == "q_day" for r in rows)


# ───────────────────────── единицы и станционный расход ─────────────────────────


KGF_MAPPING = MAPPING_YAML.replace(
    'objects:\n  "0197":',
    'pressure_unit: МПа\nobjects:\n  "0197":\n    pressure_unit: кгс/см²',
).replace('    plant: kns97pren\n    technical_place: main\n    aggregates:',
          '    plant: kns97pren\n    technical_place: main\n    aggregates:')


def test_pressure_is_converted_from_kgf(tmp_path):
    """142 кгс/см² — это 13,9 МПа; без пересчёта КПД вылезает за единицу."""
    path = tmp_path / "m.yaml"
    path.write_text(KGF_MAPPING, encoding="utf-8")
    mapping = ScadaMapping.from_yaml(path)

    rows = build_rows(iter(_ti(["KNS__#0197#PUMP_#003#POUNA,01.07.2025 0:00:00,142"])), mapping)
    p_out = next(r for r in rows if r.metric == "p_out")
    assert p_out.value == pytest.approx(13.925, abs=0.001)


def test_pressure_stays_as_is_for_mpa_objects(mapping):
    rows = build_rows(iter(_ti(["KNS__#0197#PUMP_#003#POUNA,01.07.2025 0:00:00,8,6"])), mapping)
    assert next(r for r in rows if r.metric == "p_out").value == pytest.approx(8.6)


STATION_MAPPING = MAPPING_YAML.replace(
    '''    aggregates:
      PUMP_003: "НА-3"''',
    '''    aggregates:
      PUMP_001: "НА-1"
      PUMP_002: "НА-2"
    station_flow:
      unit: SLC__001
      code: QVD__
      integral: true
      metric: q_day
      allocate_by: energy''',
)


@pytest.fixture
def station_mapping(tmp_path) -> ScadaMapping:
    path = tmp_path / "station.yaml"
    path.write_text(STATION_MAPPING, encoding="utf-8")
    return ScadaMapping.from_yaml(path)


def test_station_flow_is_split_by_energy(station_mapping):
    """Станционный расход делится пропорционально энергии работающих НА."""
    lines = [
        "KNS__#0197#SLC__#001#QVD__#I3,01.07.2025 0:00:00,100",
        "KNS__#0197#PUMP_#001#APWCN#I3,01.07.2025 0:00:00,300",
        "KNS__#0197#PUMP_#002#APWCN#I3,01.07.2025 0:00:00,100",
    ]
    rows = build_rows(iter(_ti(lines)), station_mapping)
    q = {r.aggregate_code: r.value for r in rows if r.metric == "q_day"}
    assert q["НА-1"] == pytest.approx(75.0)
    assert q["НА-2"] == pytest.approx(25.0)


def test_station_flow_is_not_written_as_a_station_row(station_mapping):
    """Иначе ядро откажется: станционный расход не распределён по агрегатам."""
    lines = [
        "KNS__#0197#SLC__#001#QVD__#I3,01.07.2025 0:00:00,100",
        "KNS__#0197#PUMP_#001#APWCN#I3,01.07.2025 0:00:00,300",
    ]
    rows = build_rows(iter(_ti(lines)), station_mapping)
    assert all(r.aggregate_code is not None for r in rows if r.metric == "q_day")


def test_idle_interval_gets_no_flow(station_mapping):
    """Если ни один агрегат не потреблял, приписывать расход некому."""
    lines = [
        "KNS__#0197#SLC__#001#QVD__#I3,01.07.2025 0:00:00,100",
        "KNS__#0197#PUMP_#001#APWCN#I3,01.07.2025 0:00:00,0",
    ]
    rows = build_rows(iter(_ti(lines)), station_mapping)
    assert [r for r in rows if r.metric == "q_day"] == []


def test_runtime_now_follows_energy_not_flow(mapping):
    """Наработка считается по энергии — так она сходится со сверкой мощности."""
    lines = [
        "KNS__#0197#PUMP_#003#APWCN#I3,01.07.2025 0:00:00,50",
        "KNS__#0197#PUMP_#003#APWCN#I3,01.07.2025 0:30:00,50",
        "KNS__#0197#PUMP_#003#QVD__#I3,01.07.2025 1:00:00,7",
    ]
    rows = build_rows(iter(_ti(lines)), mapping)
    assert next(r for r in rows if r.metric == "runtime").value == pytest.approx(1.0)
