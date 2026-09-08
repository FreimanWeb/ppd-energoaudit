from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from ppd_audit.ingest.crm_forecast import (
    CrmForecastError,
    DailyForecast,
    ForecastRun,
    aggregate_names,
    discover_runs,
    infer_interval_hours,
    iter_rows,
    parse_timestamp,
    parse_value,
    read_daily,
)


HEADER = "datetime,PRED::PUMP_001_QVD_I3,PRED::PUMP_003_QVD_I3,Q_OUT_SUM"


def _day_rows(day: str, intervals: int, na1: float, na3: float) -> list[str]:
    """Строки одних суток с шагом 30 минут."""
    rows = []
    for index in range(intervals):
        hour, minute = divmod(index * 30, 60)
        rows.append(f"{day} {hour:02d}:{minute:02d}:00,{na1},{na3},{na1 + na3}")
    return rows


def _run(tmp_path, lines: list[str], *, name: str = "base", bom: bool = True) -> ForecastRun:
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    text = "\n".join([HEADER, *lines]) + "\n"
    (directory / "forecast_by_equipment_and_total.csv").write_text(
        ("﻿" if bom else "") + text, encoding="utf-8"
    )
    return discover_runs(tmp_path)[0]


def test_parse_timestamp_accepts_pipeline_and_scada_formats():
    assert parse_timestamp("2026-07-17 22:30:00") == datetime(2026, 7, 17, 22, 30)
    assert parse_timestamp("17.07.2026 22:30:00") == datetime(2026, 7, 17, 22, 30)


def test_parse_timestamp_rejects_garbage():
    with pytest.raises(CrmForecastError):
        parse_timestamp("вчера вечером")


def test_parse_value_handles_empty_nan_and_comma():
    assert parse_value("38.87") == pytest.approx(38.87)
    assert parse_value("38,87") == pytest.approx(38.87)
    assert parse_value("") is None
    assert parse_value("nan") is None


def test_iter_rows_skips_bom_and_empty_cells(tmp_path):
    path = tmp_path / "f.csv"
    path.write_text(
        "﻿" + HEADER + "\n2026-07-17 22:30:00,,38.9,38.9\n", encoding="utf-8"
    )
    (stamp, values), = list(iter_rows(path))
    assert stamp == datetime(2026, 7, 17, 22, 30)
    assert "PRED::PUMP_001_QVD_I3" not in values
    assert values["Q_OUT_SUM"] == pytest.approx(38.9)


def test_iter_rows_requires_datetime_column(tmp_path):
    path = tmp_path / "f.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(CrmForecastError):
        list(iter_rows(path))


def test_infer_interval_hours_takes_the_most_common_step():
    stamps = [
        datetime(2026, 7, 17, 22, 0),
        datetime(2026, 7, 17, 22, 30),
        datetime(2026, 7, 17, 23, 0),
        datetime(2026, 7, 18, 2, 0),  # разрыв не должен перевесить
    ]
    assert infer_interval_hours(stamps) == pytest.approx(0.5)


def test_infer_interval_hours_falls_back_for_a_single_point():
    assert infer_interval_hours([datetime(2026, 7, 17)]) == pytest.approx(0.5)


def test_daily_totals_sum_intervals_within_a_day(tmp_path):
    run = _run(tmp_path, _day_rows("2026-07-18", 48, 1.0, 2.0))
    daily = read_daily(run)

    assert daily.total == {date(2026, 7, 18): pytest.approx(144.0)}
    assert daily.by_unit["PUMP_001"][date(2026, 7, 18)] == pytest.approx(48.0)
    assert daily.by_unit["PUMP_003"][date(2026, 7, 18)] == pytest.approx(96.0)
    assert daily.interval_hours == pytest.approx(0.5)


def test_incomplete_days_are_dropped_not_shown_as_a_dip(tmp_path):
    lines = _day_rows("2026-07-17", 3, 1.0, 2.0) + _day_rows("2026-07-18", 48, 1.0, 2.0)
    daily = read_daily(_run(tmp_path, lines))

    assert daily.partial_days == (date(2026, 7, 17),)
    assert list(daily.total) == [date(2026, 7, 18)]
    assert date(2026, 7, 17) not in daily.by_unit["PUMP_001"]


def test_units_are_renamed_to_database_aggregates(tmp_path):
    run = _run(tmp_path, _day_rows("2026-07-18", 48, 1.0, 2.0))
    daily = read_daily(run, {"PUMP_001": "НА-1", "PUMP_003": "НА-3"})

    assert set(daily.by_unit) == {"НА-1", "НА-3"}


def test_base_columns_are_ignored_only_pred_is_the_forecast(tmp_path):
    directory = tmp_path / "base"
    directory.mkdir()
    (directory / "multioutput_forecast.csv").write_text(
        "datetime,BASE::PUMP_001_QVD_I3,PRED::PUMP_001_QVD_I3,Q_OUT_SUM\n"
        + "\n".join(
            f"2026-07-18 {index // 2:02d}:{(index % 2) * 30:02d}:00,99.0,1.0,1.0"
            for index in range(48)
        )
        + "\n",
        encoding="utf-8",
    )
    daily = read_daily(discover_runs(tmp_path)[0])

    assert daily.by_unit["PUMP_001"][date(2026, 7, 18)] == pytest.approx(48.0)


def test_period_spans_first_and_last_complete_day(tmp_path):
    lines = _day_rows("2026-07-18", 48, 1.0, 2.0) + _day_rows("2026-07-19", 48, 1.0, 2.0)
    assert read_daily(_run(tmp_path, lines)).period == (date(2026, 7, 18), date(2026, 7, 19))


def test_period_is_none_without_days():
    assert DailyForecast(run=None, interval_hours=0.5).period is None


def test_empty_table_is_reported(tmp_path):
    with pytest.raises(CrmForecastError):
        read_daily(_run(tmp_path, []))


def test_run_without_a_table_is_not_discovered(tmp_path):
    (tmp_path / "пусто").mkdir()
    assert discover_runs(tmp_path) == []


def test_missing_object_dir_gives_no_runs(tmp_path):
    assert discover_runs(tmp_path / "нет") == []


def test_events_run_is_recognised_by_its_scenario_file(tmp_path):
    run = _run(tmp_path, _day_rows("2026-07-18", 48, 1.0, 2.0), name="events")
    assert run.events is False

    (tmp_path / "events" / "event_scenario_summary.csv").write_text("x\n", encoding="utf-8")
    assert discover_runs(tmp_path)[0].events is True


def test_run_json_sets_title_and_events(tmp_path):
    _run(tmp_path, _day_rows("2026-07-18", 48, 1.0, 2.0))
    (tmp_path / "base" / "run.json").write_text(
        json.dumps({"title": "Без событий", "events": False}, ensure_ascii=False),
        encoding="utf-8",
    )
    run = discover_runs(tmp_path)[0]

    assert run.title == "Без событий"
    assert run.events is False


def test_shared_metadata_is_inherited_by_every_run(tmp_path):
    _run(tmp_path, _day_rows("2026-07-18", 48, 1.0, 2.0))
    (tmp_path / "model_metadata.json").write_text(
        json.dumps({"object_id": "0197", "recommended_model": "Multi Hybrid ARX"}),
        encoding="utf-8",
    )
    run = discover_runs(tmp_path)[0]

    assert run.object_id == "0197"
    assert run.model == "Multi Hybrid ARX"


def test_broken_metadata_does_not_break_discovery(tmp_path):
    _run(tmp_path, _day_rows("2026-07-18", 48, 1.0, 2.0))
    (tmp_path / "model_metadata.json").write_text("{не json", encoding="utf-8")

    assert discover_runs(tmp_path)[0].object_id is None


def test_aggregate_names_reads_the_scada_mapping():
    objects = {"0197": {"aggregates": {"PUMP_001": "НА-1", "PUMP_003": "НА-3"}}}

    assert aggregate_names(objects, "0197") == {"PUMP_001": "НА-1", "PUMP_003": "НА-3"}
    assert aggregate_names(objects, "5401") == {}
    assert aggregate_names(objects, None) == {}


def test_missing_table_is_reported_with_the_folder(tmp_path):
    run = ForecastRun(path=tmp_path / "нет", code="нет", title="нет", events=False)
    with pytest.raises(CrmForecastError):
        _ = run.table
