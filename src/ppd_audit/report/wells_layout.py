"""Раскладка графа скважин силами.

Узлы отталкиваются друг от друга, связи стягивают их обратно — связанные
скважины собираются в группы, несвязанные расходятся. В отличие от круга
такая раскладка показывает структуру: какие скважины работают сообща.

Алгоритм — Фрухтерман–Рейнгольд. Раскладка детерминирована: одинаковый
вход даёт одинаковую картинку, иначе схема прыгала бы при каждом
обновлении страницы.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence


ITERATIONS = 400
INITIAL_TEMPERATURE = 0.12
MIN_DISTANCE = 1e-4

# Отталкивание против притяжения. Связей рисуется много, и при равном балансе
# всё стягивается в один комок: узлы налезают друг на друга и подписи не читаются.
REPULSION = 2.2
ATTRACTION_BASE = 0.08


def _circle(nodes: Sequence[str]) -> dict[str, list[float]]:
    """Стартовые позиции по кругу: детерминированы и не дают совпадений."""
    count = len(nodes)
    return {
        node: [
            math.cos(2 * math.pi * index / count),
            math.sin(2 * math.pi * index / count),
        ]
        for index, node in enumerate(nodes)
    }


def _normalize(positions: dict[str, list[float]]) -> dict[str, tuple[float, float]]:
    """Вписать раскладку в квадрат [-1, 1] с сохранением пропорций."""
    xs = [point[0] for point in positions.values()]
    ys = [point[1] for point in positions.values()]
    span = max(max(xs) - min(xs), max(ys) - min(ys), MIN_DISTANCE)
    center_x = (max(xs) + min(xs)) / 2
    center_y = (max(ys) + min(ys)) / 2
    return {
        node: (2 * (point[0] - center_x) / span, 2 * (point[1] - center_y) / span)
        for node, point in positions.items()
    }


def spring_layout(
    nodes: Sequence[str],
    edges: Iterable[tuple[str, str, float]],
    *,
    iterations: int = ITERATIONS,
) -> dict[str, tuple[float, float]]:
    """Позиции узлов в квадрате [-1, 1].

    ``edges`` — тройки (откуда, куда, вес); вес тянет сильнее, поэтому
    сильно связанные скважины оказываются рядом.
    """
    if not nodes:
        return {}
    if len(nodes) == 1:
        return {nodes[0]: (0.0, 0.0)}

    positions = _circle(nodes)
    known = set(nodes)
    links = [
        (source, target, max(weight, 0.0))
        for source, target, weight in edges
        if source in known and target in known and source != target
    ]

    k = math.sqrt(1.0 / len(nodes))
    temperature = INITIAL_TEMPERATURE

    for _ in range(iterations):
        shift = {node: [0.0, 0.0] for node in nodes}

        for index, first in enumerate(nodes):
            for second in nodes[index + 1 :]:
                dx = positions[first][0] - positions[second][0]
                dy = positions[first][1] - positions[second][1]
                distance = max(math.hypot(dx, dy), MIN_DISTANCE)
                force = REPULSION * k * k / distance
                shift[first][0] += dx / distance * force
                shift[first][1] += dy / distance * force
                shift[second][0] -= dx / distance * force
                shift[second][1] -= dy / distance * force

        for source, target, weight in links:
            dx = positions[source][0] - positions[target][0]
            dy = positions[source][1] - positions[target][1]
            distance = max(math.hypot(dx, dy), MIN_DISTANCE)
            force = distance * distance / k * (ATTRACTION_BASE + weight)
            shift[source][0] -= dx / distance * force
            shift[source][1] -= dy / distance * force
            shift[target][0] += dx / distance * force
            shift[target][1] += dy / distance * force

        for node in nodes:
            dx, dy = shift[node]
            step = max(math.hypot(dx, dy), MIN_DISTANCE)
            limit = min(step, temperature)
            positions[node][0] += dx / step * limit
            positions[node][1] += dy / step * limit

        temperature *= 1.0 - 1.0 / iterations

    return _normalize(positions)
