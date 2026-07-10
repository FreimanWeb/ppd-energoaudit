"""Распределительные узлы: сведение материального баланса и локализация невязок.

ТЗ: сведение балансов потоков, локализация невязок по узлам.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NodeBalance:
    node_id: str
    inflow_total: float
    outflow_total: float
    residual: float          # приход − расход
    relative: float          # доля от прихода
    anomaly: bool
    inflows: dict = field(default_factory=dict)
    outflows: dict = field(default_factory=dict)


def material_balance(node_id: str, inflows: dict[str, float], outflows: dict[str, float],
                     threshold: float = 0.05) -> NodeBalance:
    """Материальный баланс узла: Σприход − Σрасход; флаг невязки > порога.

    inflows/outflows: {ветка: расход, м³/ч или м³/сут}.
    """
    qin = sum(inflows.values())
    qout = sum(outflows.values())
    residual = qin - qout
    rel = residual / qin if qin else 0.0
    return NodeBalance(node_id=node_id, inflow_total=qin, outflow_total=qout,
                       residual=residual, relative=rel, anomaly=abs(rel) > threshold,
                       inflows=dict(inflows), outflows=dict(outflows))


def localize_imbalance(balances: list[NodeBalance]) -> list[NodeBalance]:
    """Отсортировать узлы по абсолютной невязке (для локализации проблем)."""
    return sorted(balances, key=lambda b: abs(b.residual), reverse=True)
