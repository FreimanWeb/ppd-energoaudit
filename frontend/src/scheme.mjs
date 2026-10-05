/** @param {import('./types').Topology} topology */
export function layoutTopology(topology) {
  const maxY = Math.max(0, ...topology.nodes.map((n) => n.y));
  const minX = Math.min(0, ...topology.nodes.map((n) => n.x));
  const nodes = topology.nodes.map((n) => ({
    ...n,
    px: 110 + (n.x - minX) * 220,
    py: 100 + (maxY - n.y) * 150 + (n.type === "reservoir" ? 160 : 0),
  }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const edges = topology.edges.flatMap((edge) => {
    const source = byId.get(edge.from),
      target = byId.get(edge.to);
    if (!source || !target) return [];
    const x0 =
      source.px +
      (source.type === "wells" ? 0 : source.type === "pump" ? 72 : 40);
    const y0 = source.py + (source.type === "wells" ? 160 : 0);
    const x1 =
      target.px -
      (target.type === "pump" ? 72 : target.type === "reservoir" ? 0 : 40);
    const middle = (x0 + x1) / 2;
    return [
      {
        ...edge,
        source,
        target,
        middle,
        path: `M${x0} ${y0} H${middle} V${target.py} H${x1}`,
      },
    ];
  });
  return {
    nodes,
    edges,
    width: Math.max(600, ...nodes.map((n) => n.px + 140)),
    height: Math.max(
      250,
      ...nodes.map((n) => n.py + (n.type === "wells" ? 190 : 90)),
    ),
  };
}

/** @param {ReturnType<typeof layoutTopology>['edges'][number]} edge
 * @param {string} aggregate
 * @param {import('./types').Snapshot | null} snapshot */
export function pressureForEdge(edge, aggregate, snapshot) {
  if (!snapshot) return null;
  if (edge.target.type === "pump" && edge.target.agg === aggregate)
    return snapshot.p_in_mpa;
  if (edge.source.type === "pump" && edge.source.agg === aggregate)
    return snapshot.p_out_mpa;
  return null;
}
