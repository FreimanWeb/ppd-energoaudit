import test from "node:test";
import assert from "node:assert/strict";
import {
  forecastTraces,
  wellSeries,
  filterEdges,
  sumDaily,
} from "./chartData.mjs";
test("forecast keeps interval order and distinguishes history from future", () => {
  const traces = forecastTraces({
    history: [{ period: -1, value: 7 }],
    forecast: [{ period: 1, value: 9, lower: 8, upper: 11 }],
    naive_baseline: 7,
  });
  assert.deepEqual(traces[0].y, [7]);
  assert.deepEqual(traces[1].y, [8]);
  assert.deepEqual(traces[2].y, [11]);
  assert.equal(traces[2].fill, "tonexty");
  assert.deepEqual(traces[3].y, [9]);
});
test("well monthly series never turns missing fact into zero", () => {
  assert.deepEqual(
    wellSeries(
      {
        totals: [{ month: "2026-01-01", fact: null }],
        rows: [
          { month: "2026-01-01", well: "1", fact: 0 },
          { month: "2026-02-01", well: "1", fact: null },
        ],
      },
      "1",
    ).map((x) => x.fact),
    [0, null],
  );
});
test("edge strength threshold preserves actual selected links only", () => {
  const edges = [
    { source: "1", target: "2", strength: 0.4 },
    { source: "2", target: "3", strength: 0.8 },
  ];
  assert.deepEqual(filterEdges(edges, 0.5, "2"), [edges[1]]);
  assert.deepEqual(filterEdges(edges, 0, "1"), [edges[0]]);
});
test("daily aggregate comparison sums same-date observed volumes only", () => {
  assert.deepEqual(
    sumDaily([
      ["2026-01-01", 3],
      ["2026-01-01", 2],
      ["2026-01-03", 4],
    ]),
    [
      ["2026-01-01", 5],
      ["2026-01-03", 4],
    ],
  );
});

const { lossChartData } = await import("./lossChartData.mjs");
test("loss charts retain signed components and supplied useful power", () => {
  const result = lossChartData(100, [
    { name: "Полезная", power_kw: 60, share: 0.6, category: "полезная" },
    { name: "Потери", power_kw: 45, share: 0.45, category: "потеря" },
    { name: "Коррекция", power_kw: -5, share: -0.05, category: "потеря" },
  ]);
  assert.deepEqual(result.waterfall.y, [100, -45, 5, 60]);
  assert.equal(result.waterfall.measure.at(-1), "absolute");
  assert.deepEqual(result.sankey.link.value, [60, 45]);
  assert.deepEqual(
    result.shares.map((t) => t.x[0]),
    [60, 45, -5],
  );
});

const { downtimeForWell } = await import('./chartData.mjs');
test('downtime markers use canonical well key and require an actual reason',()=>{
 const rows=[{well:'3592Д/2',well_key:'3592Д'}];
 const downtime=[{well:'3592Д',well_key:'3592Д',reason:'Ремонт',since:'2026-09-10T12:00'}];
 assert.equal(downtimeForWell('3592Д/2',rows,downtime),downtime[0]);
 assert.equal(downtimeForWell('2015',rows,downtime),null);
 assert.equal(downtimeForWell('3592Д/2',rows,[{...downtime[0],reason:''}]),null);
});
