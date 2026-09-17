from __future__ import annotations

import math

from ppd_audit.report.wells_layout import spring_layout


def _distance(positions, first, second) -> float:
    return math.dist(positions[first], positions[second])


def test_empty_graph_gives_no_positions():
    assert spring_layout([], []) == {}


def test_single_node_sits_in_the_centre():
    assert spring_layout(["2015"], []) == {"2015": (0.0, 0.0)}


def test_every_node_gets_a_position():
    nodes = ["2015", "2017", "2019", "2031"]
    positions = spring_layout(nodes, [("2015", "2017", 0.8)], iterations=40)

    assert set(positions) == set(nodes)


def test_positions_stay_inside_the_unit_box():
    nodes = [str(index) for index in range(12)]
    edges = [(str(i), str(i + 1), 0.5) for i in range(11)]
    positions = spring_layout(nodes, edges, iterations=60)

    assert all(-1.001 <= x <= 1.001 and -1.001 <= y <= 1.001 for x, y in positions.values())


def test_layout_is_deterministic():
    nodes = ["a", "b", "c", "d", "e"]
    edges = [("a", "b", 0.9), ("c", "d", 0.4)]

    assert spring_layout(nodes, edges, iterations=50) == spring_layout(
        nodes, edges, iterations=50
    )


def test_connected_nodes_end_up_closer_than_unconnected():
    """Смысл раскладки: связанные скважины собираются рядом."""
    nodes = ["a", "b", "c", "d"]
    positions = spring_layout(nodes, [("a", "b", 1.0)], iterations=300)

    assert _distance(positions, "a", "b") < _distance(positions, "a", "c")
    assert _distance(positions, "a", "b") < _distance(positions, "a", "d")


def test_stronger_link_pulls_closer():
    nodes = ["a", "b", "c", "d"]
    edges = [("a", "b", 1.0), ("c", "d", 0.05)]
    positions = spring_layout(nodes, edges, iterations=300)

    assert _distance(positions, "a", "b") < _distance(positions, "c", "d")


def test_edges_to_unknown_nodes_are_ignored():
    nodes = ["a", "b"]
    positions = spring_layout(nodes, [("a", "нет-такой", 1.0)], iterations=30)

    assert set(positions) == {"a", "b"}


def test_self_loops_are_ignored():
    positions = spring_layout(["a", "b"], [("a", "a", 1.0)], iterations=30)

    assert set(positions) == {"a", "b"}


def test_nodes_do_not_collapse_onto_one_point():
    nodes = ["a", "b", "c", "d", "e", "f"]
    edges = [(first, second, 1.0) for first in nodes for second in nodes if first < second]
    positions = spring_layout(nodes, edges, iterations=200)

    pairs = [
        _distance(positions, first, second)
        for index, first in enumerate(nodes)
        for second in nodes[index + 1 :]
    ]
    assert min(pairs) > 0.05


def test_negative_weight_is_clamped_not_repelling():
    nodes = ["a", "b", "c"]
    positions = spring_layout(nodes, [("a", "b", -5.0)], iterations=60)

    assert all(math.isfinite(x) and math.isfinite(y) for x, y in positions.values())


def test_zero_iterations_still_returns_a_valid_layout():
    positions = spring_layout(["a", "b", "c"], [], iterations=0)

    assert set(positions) == {"a", "b", "c"}
    assert all(-1.001 <= x <= 1.001 for x, _ in positions.values())


def test_many_nodes_are_laid_out_in_reasonable_time():
    nodes = [str(index) for index in range(34)]
    edges = [(str(i), str((i * 7) % 34), 0.3) for i in range(60)]
    positions = spring_layout(nodes, edges, iterations=120)

    assert len(positions) == 34
    assert all(math.isfinite(value) for point in positions.values() for value in point)


def test_weight_of_zero_still_links_nodes():
    """Нулевой вес — не «связи нет»: линия нарисована, значит узлы связаны."""
    nodes = ["a", "b", "c", "d"]
    positions = spring_layout(nodes, [("a", "b", 0.0)], iterations=300)

    assert _distance(positions, "a", "b") < _distance(positions, "a", "c")


def test_layout_spans_the_box_not_a_corner():
    nodes = [str(index) for index in range(10)]
    positions = spring_layout(nodes, [], iterations=80)
    xs = [x for x, _ in positions.values()]
    ys = [y for _, y in positions.values()]

    assert max(xs) - min(xs) > 1.0 or max(ys) - min(ys) > 1.0
    assert abs((max(xs) + min(xs)) / 2) < 1e-6
    assert abs((max(ys) + min(ys)) / 2) < 1e-6


def test_positions_are_plain_float_pairs():
    positions = spring_layout(["a", "b"], [("a", "b", 0.5)], iterations=10)
    point = positions["a"]

    assert isinstance(point, tuple)
    assert len(point) == 2
    assert all(isinstance(value, float) for value in point)


def test_long_run_does_not_blow_up_coordinates():
    nodes = [str(index) for index in range(8)]
    edges = [(str(i), str(i + 1), 1.0) for i in range(7)]
    positions = spring_layout(nodes, edges, iterations=1000)

    assert all(abs(x) <= 1.001 and abs(y) <= 1.001 for x, y in positions.values())


def test_a_disconnected_node_does_not_squash_the_rest():
    """Узел без связей уезжал далеко и растягивал масштаб: остальные схлопывались."""
    core = ["a", "b", "c", "d", "e", "f"]
    nodes = [*core, "одинокая"]
    edges = [(first, second, 0.6) for first in core for second in core if first < second]
    positions = spring_layout(nodes, edges)

    spread = [
        _distance(positions, first, second)
        for index, first in enumerate(core)
        for second in core[index + 1 :]
    ]
    assert min(spread) > 0.1
