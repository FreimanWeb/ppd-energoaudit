import test from "node:test";
import assert from "node:assert/strict";
import { layoutTopology, pressureForEdge } from "./scheme.mjs";

test("all pump branches and actual edges survive layout", () => {
  const topology = {
    nodes: [
      { id: "source", type: "source", x: 0, y: 0 },
      { id: "a", type: "pump", agg: "a", x: 1, y: 1 },
      { id: "b", type: "pump", agg: "b", x: 1, y: -1 },
      { id: "end", type: "meter", x: 2, y: 0 },
    ],
    edges: [
      { from: "source", to: "a" },
      { from: "source", to: "b" },
      { from: "a", to: "end" },
      { from: "b", to: "end" },
    ],
  };
  const result = layoutTopology(topology);
  assert.equal(result.nodes.length, 4);
  assert.equal(result.edges.length, 4);
  assert.notEqual(result.nodes[1].py, result.nodes[2].py);
  assert.equal(
    pressureForEdge(result.edges[0], "a", { p_in_mpa: 1, p_out_mpa: 9 }),
    1,
  );
  assert.equal(
    pressureForEdge(result.edges[1], "a", { p_in_mpa: 1, p_out_mpa: 9 }),
    null,
  );
  assert.equal(
    pressureForEdge(result.edges[2], "a", { p_in_mpa: 1, p_out_mpa: 9 }),
    9,
  );
});
