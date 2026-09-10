from __future__ import annotations

import json
from datetime import date

import pytest

from ppd_audit.ingest.crm_wells import (
    CrmWellsError,
    Edge,
    WellRun,
    WellsGraph,
    discover_runs,
    parse_month,
    parse_value,
    read_graph,
    read_report,
)


HEADER = (
    "КНС,Период,Нагн. скваж.,Закачка м3/мес базовый прогноз,Закачка м3/мес прогноз,"
    "Доля базовый прогноз,Доля прогноз,Руст базовый прогноз,Руст прогноз,"
    "Суммарная закачка прогноз,Закачка м3/мес факт,Руст факт"
)


def _row(month: str, well: str, base: float, forecast: float, fact: str = "") -> str:
    return (
        f"97,{month},{well},{base},{forecast},0.02,0.02,60.0,61.0,44086.5,{fact},62.0"
    )


def _run(tmp_path, lines: list[str], *, name: str = "wells") -> WellRun:
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "predicted_injector_report_like.csv").write_text(
        "﻿" + "\n".join([HEADER, *lines]) + "\n", encoding="utf-8"
    )
    return discover_runs(tmp_path)[0]


def test_parse_month_accepts_both_orders():
    assert parse_month("04.2026") == date(2026, 4, 1)
    assert parse_month("2026-04") == date(2026, 4, 1)


def test_parse_month_rejects_garbage():
    with pytest.raises(CrmWellsError):
        parse_month("апрель")


def test_parse_value_handles_empty_and_comma():
    assert parse_value("1042,38") == pytest.approx(1042.38)
    assert parse_value("") is None
    assert parse_value(None) is None
    assert parse_value("nan") is None


def test_report_collects_months_and_wells(tmp_path):
    run = _run(tmp_path, [
        _row("04.2026", "2015", 1042.0, 922.0, "2088.7"),
        _row("05.2026", "2015", 1000.0, 900.0, "2000.0"),
        _row("04.2026", "2017А", 1781.0, 1576.0, "1651.9"),
    ])
    report = read_report(run)

    assert report.months == (date(2026, 4, 1), date(2026, 5, 1))
    assert report.wells == ("2015", "2017А")
    assert report.has_fact is True


def test_report_without_fact_is_marked(tmp_path):
    report = read_report(_run(tmp_path, [_row("04.2026", "2015", 1042.0, 922.0)]))

    assert report.has_fact is False
    assert report.rows[0].fact is None


def test_monthly_totals_sum_every_well(tmp_path):
    run = _run(tmp_path, [
        _row("04.2026", "2015", 1000.0, 900.0, "1100.0"),
        _row("04.2026", "2017", 2000.0, 1800.0, "2200.0"),
    ])
    totals = read_report(run).totals()

    assert len(totals) == 1
    assert totals[0].base == pytest.approx(3000.0)
    assert totals[0].forecast == pytest.approx(2700.0)
    assert totals[0].fact == pytest.approx(3300.0)


def test_totals_report_no_fact_as_none_not_zero(tmp_path):
    """Ноль и «факта нет» — разные вещи: ноль нарисовал бы провал закачки."""
    totals = read_report(_run(tmp_path, [_row("04.2026", "2015", 1000.0, 900.0)])).totals()

    assert totals[0].fact is None


def test_deviation_percent_compares_forecast_with_fact(tmp_path):
    report = read_report(_run(tmp_path, [_row("04.2026", "2015", 1000.0, 900.0, "1000.0")]))

    assert report.rows[0].deviation_percent == pytest.approx(-10.0)


def test_deviation_is_none_without_fact_or_on_zero_fact(tmp_path):
    report = read_report(_run(tmp_path, [
        _row("04.2026", "2015", 1000.0, 900.0),
        _row("04.2026", "2017", 1000.0, 900.0, "0"),
    ]))

    assert all(row.deviation_percent is None for row in report.rows)


def test_for_month_filters_rows(tmp_path):
    run = _run(tmp_path, [
        _row("04.2026", "2015", 1000.0, 900.0),
        _row("05.2026", "2017", 1000.0, 900.0),
    ])
    rows = read_report(run).for_month(date(2026, 5, 1))

    assert [row.well for row in rows] == ["2017"]


def test_empty_report_is_reported(tmp_path):
    with pytest.raises(CrmWellsError):
        read_report(_run(tmp_path, []))


def test_rows_without_month_or_well_are_skipped(tmp_path):
    run = _run(tmp_path, [",,,,,,,,,,,", _row("04.2026", "2015", 1000.0, 900.0)])

    assert len(read_report(run).rows) == 1


def test_run_json_sets_title_and_mode(tmp_path):
    _run(tmp_path, [_row("04.2026", "2015", 1000.0, 900.0)])
    (tmp_path / "wells" / "run.json").write_text(
        json.dumps({"title": "Проверка на скрытых месяцах", "mode": "heldout"}),
        encoding="utf-8",
    )
    run = discover_runs(tmp_path)[0]

    assert run.title == "Проверка на скрытых месяцах"
    assert run.mode == "heldout"


def test_run_without_report_is_not_discovered(tmp_path):
    (tmp_path / "пусто").mkdir()
    assert discover_runs(tmp_path) == []


def test_missing_object_dir_gives_no_runs(tmp_path):
    assert discover_runs(tmp_path / "нет") == []


def test_missing_report_is_reported_with_the_folder(tmp_path):
    run = WellRun(path=tmp_path / "нет", code="нет", title="нет")
    with pytest.raises(CrmWellsError):
        _ = run.report


def test_graph_reads_edges_and_centrality(tmp_path):
    run = _run(tmp_path, [_row("04.2026", "2015", 1000.0, 900.0)])
    (run.path / "loaded_model_injector_interdependence_edges.csv").write_text(
        "source,target,combined_strength,combined_signed\n"
        "2162,2163,0.82,0.29\n2165,2166,0.73,0.26\n",
        encoding="utf-8",
    )
    (run.path / "loaded_model_injector_dependency_centrality.csv").write_text(
        "injector,strength_sum,degree_centrality,betweenness_centrality,"
        "top_neighbor,top_neighbor_strength\n4394,3.62,0.4,0.18,2026,0.37\n",
        encoding="utf-8",
    )
    graph = read_graph(discover_runs(tmp_path)[0])

    assert len(graph.edges) == 2
    assert graph.centrality[0].well == "4394"
    assert graph.centrality[0].top_neighbor == "2026"


def test_graph_is_empty_when_files_are_absent(tmp_path):
    graph = read_graph(_run(tmp_path, [_row("04.2026", "2015", 1000.0, 900.0)]))

    assert graph.edges == ()
    assert graph.centrality == ()


def test_neighbours_are_sorted_by_strength():
    graph = WellsGraph(edges=(
        Edge("2015", "2017", 0.3, 0.1),
        Edge("2015", "2019", 0.8, -0.2),
        Edge("2077", "2015", 0.9, 0.4),
    ))
    assert [e.target for e in graph.neighbours("2015")] == ["2019", "2017"]


def test_neighbours_respect_the_limit():
    edges = tuple(Edge("2015", str(i), i / 10, 0.1) for i in range(1, 8))
    assert len(WellsGraph(edges=edges).neighbours("2015", limit=3)) == 3


def test_strongest_drops_the_mirror_edge():
    """Пайплайн пишет связь дважды — в обе стороны; на схеме нужна одна линия."""
    graph = WellsGraph(edges=(
        Edge("2162", "2163", 0.82, 0.29),
        Edge("2163", "2162", 0.82, 0.26),
        Edge("2165", "2166", 0.73, 0.26),
    ))
    strongest = graph.strongest()

    assert len(strongest) == 2
    assert {tuple(sorted((e.source, e.target))) for e in strongest} == {
        ("2162", "2163"),
        ("2165", "2166"),
    }


def test_strongest_respects_the_limit():
    edges = tuple(Edge(str(i), str(i + 100), i / 100, 0.1) for i in range(1, 20))
    assert len(WellsGraph(edges=edges).strongest(limit=5)) == 5
