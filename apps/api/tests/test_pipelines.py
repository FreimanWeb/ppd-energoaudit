from __future__ import annotations

from datetime import datetime

import pytest

from ppd_audit.ingest.pipelines import normalize_well, parse_pipelines, well_from_file_code


def _row(pipeline: str, start: str, end: str, state: str, section: tuple, **extra) -> tuple:
    """Строка выгрузки реестра: 46 колонок, заполнены только нужные."""
    row = [None] * 46
    row[0] = 1
    row[4], row[5], row[6] = pipeline, start, end
    row[9] = extra.get("pipeline_length", 1000)
    row[11] = extra.get("purpose", "Разводящий")
    row[13] = "Вода сточная"
    row[19] = extra.get("temperature", 10)
    row[20] = 122
    row[24], row[25], row[26] = section[0], section[1], section[1] - section[0]
    row[27] = datetime(2010, 1, 1)
    row[28] = state
    row[29] = extra.get("pipe_type", "МПТ")
    row[30], row[31] = extra.get("outer", 114), extra.get("wall", 9)
    row[32] = extra.get("coating", "ПЭ")
    row[34] = "Сталь 20"
    return tuple(row)


HEADER = [(None, None, "Наименование организации"), ("№", "Старый идентификатор")]


def test_only_working_sections_are_taken():
    rows = HEADER + [
        _row("КНС - Скв 1 - 1", "КНС", "Скв 1", "В работе", (0, 400)),
        _row("КНС - Скв 1 - 1", "КНС", "Скв 1", "Участок заменен", (0, 400)),
        _row("КНС - Скв 1 - 1", "КНС", "Скв 1", "В работе", (400, 1000)),
        _row("КНС - Скв 2 - 1", "КНС", "Скв 2", "В ликвидации", (0, 500)),
    ]
    pipelines = parse_pipelines(rows)

    assert [p.name for p in pipelines] == ["КНС - Скв 1 - 1"]
    assert pipelines[0].active_length_m == pytest.approx(1000.0)
    assert [s.start_m for s in pipelines[0].sections] == [0, 400]


def test_inner_diameter_is_outer_minus_two_walls():
    rows = HEADER + [
        _row("КНС - Скв 1 - 1", "КНС", "Скв 1", "В работе", (0, 100), outer=89, wall=7)
    ]
    section = parse_pipelines(rows)[0].sections[0]

    assert section.inner_mm == pytest.approx(75.0)
    assert section.inner_m == pytest.approx(0.075)


def test_sections_without_geometry_are_skipped():
    rows = HEADER + [
        _row("КНС - Скв 1 - 1", "КНС", "Скв 1", "В работе", (0, 100), outer=0),
        _row("КНС - Скв 2 - 1", "КНС", "Скв 2", "В работе", (0, 100), outer=10, wall=6),
    ]

    assert parse_pipelines(rows) == []


def test_pipeline_knows_its_well():
    rows = HEADER + [_row("КНС - Скв 8323А - 1", "КНС", "Скв 8323А", "В работе", (0, 50))]

    assert parse_pipelines(rows)[0].well == "8323А"


def test_missing_header_is_an_error():
    with pytest.raises(ValueError):
        parse_pipelines([("нет", "заголовка")])


@pytest.mark.parametrize(
    ("text", "well"),
    [
        ("Скв 26228", "26228"),
        ("Скв 15150Д", "15150Д"),
        ("Скв 8323A", "8323А"),  # латинская A из выгрузки
        ("БГ-1 (КНС-54)", None),
        (None, None),
    ],
)
def test_well_numbers_are_normalized(text, well):
    assert normalize_well(text) == well


def test_file_codes_match_registry_well_numbers():
    assert well_from_file_code("15150d") == "15150Д"
    assert well_from_file_code("7583a") == "7583А"
    assert well_from_file_code("26228") == "26228"
