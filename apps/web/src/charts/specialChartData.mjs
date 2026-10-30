/** Позиция маркера на верхней полуокружности общей шкалы КПД. */
export function gaugePoint(value, max, cx, cy, radius) {
  const ratio = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  const angle = Math.PI * (1 - ratio);
  return { x: cx + radius * Math.cos(angle), y: cy - radius * Math.sin(angle) };
}

/** У входа нет измеренного итога в Sankey-model: сумма положительных потоков не заменяет его. */
export function flowNodeValues(count, links) {
  return Array.from({ length: count }, (_, index) => {
    const incoming = links.filter(link => link.target === index && link.value > 0);
    if (!incoming.length && links.some(link => link.source === index && link.value > 0)) return null;
    return incoming.reduce((sum, link) => sum + link.value, 0);
  });
}

/** D3 размещает только узлы с положительным потоком; originalIndex связывает их с исходными статьями. */
export function activeFlowGraph(nodes, links) {
  const positive = links.filter(link => link.value > 0);
  const connected = new Set(positive.flatMap(link => [link.source, link.target]));
  const active = nodes.flatMap((node, originalIndex) => connected.has(originalIndex) ? [{ ...node, originalIndex }] : []);
  const indices = new Map(active.map((node, index) => [node.originalIndex, index]));
  return {
    nodes: active,
    links: positive.map(link => ({ ...link, source: indices.get(link.source), target: indices.get(link.target) })),
  };
}
