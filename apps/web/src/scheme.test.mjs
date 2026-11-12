import test from "node:test";
import assert from "node:assert/strict";
import { layoutTopology, pressureForEdge } from "./features/scheme/schemeLayout.mjs";

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
  assert.equal(result.nodes[1].px-result.nodes[0].px,280);
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


test("parallel pump pressure labels use each branch at the shared timestamp", () => {
  const edge = {target: {type: "pump", agg: "b"}, source: {type: "source"}};
  const pressures = {a: {p_in_mpa: 1, p_out_mpa: 9}, b: {p_in_mpa: 2, p_out_mpa: 12}};
  assert.equal(pressureForEdge(edge, "a", pressures.a, pressures), 2);
  assert.equal(pressureForEdge({...edge, target: {type: "pump", agg: "missing"}}, "a", pressures.a, pressures), null);
});

test('network valves and well chokes stay separate and the original topology is preserved',()=>{
  const topology={nodes:[
    {id:'source',type:'source',x:0,y:0},
    {id:'pump',type:'pump',x:1,y:0},
    {id:'bg',type:'manifold',x:2,y:0},
    {id:'zra',type:'valve',x:3,y:0,label:'ЗРА / штуцеры'},
    {id:'wells',type:'wells',x:4,y:0},
  ],edges:[{from:'bg',to:'zra'},{from:'zra',to:'wells',kind:'throttle'}]};
  const original=JSON.stringify(topology);
  const graph=layoutTopology(topology);
  const zra=graph.nodes.find(node=>node.id==='zra');
  const choke=graph.nodes.find(node=>node.type==='choke');
  const wells=graph.nodes.find(node=>node.id==='wells');
  const bg=graph.nodes.find(node=>node.id==='bg');
  assert.ok(choke);
  assert.equal(zra.type,'valve');
  assert.equal(zra.label,'ЗРА');
  assert.equal(zra.px-bg.px,280);
  assert.equal(wells.px-choke.px,100);
  assert.ok(zra.px<choke.px);
  assert.ok(graph.edges.some(edge=>edge.from==='zra' && edge.to===choke.id));
  assert.ok(graph.edges.some(edge=>edge.from===choke.id && edge.to==='wells' && edge.kind==='throttle'));
  assert.equal(JSON.stringify(topology),original);
  const ordinary=layoutTopology({...topology,edges:topology.edges.map(edge=>({...edge,kind:undefined}))});
  assert.equal(ordinary.nodes.filter(node=>node.type==='choke').length,0);
});
