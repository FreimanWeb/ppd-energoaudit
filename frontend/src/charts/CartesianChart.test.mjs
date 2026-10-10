import test from "node:test";
import assert from "node:assert/strict";
import * as geometry from "./cartesianGeometry.mjs";
const series = (extra = {}) => ({
  id: "a",
  name: "Факт",
  type: "line",
  color: "#247457",
  width: 2,
  curve: "linear",
  showLegend: true,
  connectNulls: false,
  points: [
    { x: 0, y: 3 },
    { x: 1, y: null },
    { x: 2, y: 7 },
  ],
  ...extra,
});
const model = (extra = {}) => ({
  kind: "cartesian",
  variant: "series",
  title: "Режим",
  height: 360,
  margin: { top: 10, right: 10, bottom: 20, left: 20 },
  series: [series()],
  data: [],
  xAxis: { type: "number", label: "Q" },
  yAxis: { type: "number", label: "H" },
  horizontal: false,
  stacked: false,
  references: [],
  annotations: [],
  ...extra,
});
test("divergent stacked segments retain independent signed intervals and zero baseline", () => {
  assert.equal(typeof geometry.barIntervals, "function");
  const m = model({
    horizontal: true,
    stacked: true,
    series: [
      series({ id: "a", type: "bar", points: [{ x: "", y: 60 }] }),
      series({ id: "b", type: "bar", points: [{ x: "", y: -5 }] }),
      series({ id: "c", type: "bar", points: [{ x: "", y: 20 }] }),
    ],
    xAxis: { type: "number", label: "%" },
    yAxis: { type: "category", label: "" },
  });
  const bars = geometry.barIntervals(m);
  assert.deepEqual(
    bars.map((b) => [b.series.id, b.start, b.end, b.value]),
    [
      ["a", 0, 60, 60],
      ["b", 0, -5, -5],
      ["c", 60, 80, 20],
    ],
  );
  assert.deepEqual(geometry.chartDomains(m).x, [-5, 80]);
});
test("null gaps survive line splitting, and viewport retains boundary points without deleting raw data", () => {
  assert.equal(typeof geometry.lineRuns, "function");
  const points = series().points;
  assert.deepEqual(geometry.lineRuns(points, false), [
    [points[0]],
    [points[2]],
  ]);
  assert.deepEqual(geometry.lineRuns(points, true), [[points[0], points[2]]]);
  const dense = Array.from({ length: 601 }, (_, x) => ({ x, y: x }));
  assert.deepEqual(
    geometry.viewPoints(dense, [100, 102]).map((p) => p.x),
    [99, 100, 101, 102, 103],
  );
  assert.equal(dense.length, 601);
});
test("waterfall honours server-supplied before/after ranges and annual CAPEX reference extends value domain", () => {
  assert.equal(typeof geometry.chartDomains, "function");
  const w = model({
    variant: "waterfall",
    series: [],
    waterfall: [
      { label: "Подвод", start: 0, end: 100, value: 100, color: "green" },
      { label: "Потери", start: 100, end: 55, value: -45, color: "red" },
      { label: "Коррекция", start: 55, end: 60, value: 5, color: "amber" },
    ],
  });
  assert.deepEqual(
    geometry.barIntervals(w).map((b) => [b.start, b.end, b.value]),
    [
      [0, 100, 100],
      [100, 55, -45],
      [55, 60, 5],
    ],
  );
  assert.deepEqual(geometry.chartDomains(w).y, [0, 100]);
  const m = model({ references: [{ axis: "y", value: 200, label: "CAPEX" }] });
  assert.equal(geometry.chartDomains(m).y[1], 200);
});
test("confidence intervals supply actual low/high extents and time viewport leaves category labels intact", () => {
  assert.equal(typeof geometry.chartDomains, "function");
  const m = model({
    series: [
      series({
        type: "band",
        points: [
          { x: 10, y: 14, low: 8, high: 14 },
          { x: 20, y: 18, low: 7, high: 18 },
        ],
      }),
    ],
    xAxis: { type: "time", label: "Дата" },
  });
  assert.deepEqual(geometry.chartDomains(m).y, [7, 18]);
  assert.deepEqual(geometry.chartDomains(m, [], [12, 16]).x, [12, 16]);
  const bars = model({
    series: [
      series({
        type: "bar",
        points: [
          { x: "2026-10-10", y: 5 },
          { x: "Выход", y: null },
        ],
      }),
    ],
    xAxis: { type: "category", label: "" },
  });
  assert.deepEqual(geometry.chartDomains(bars).x, ["2026-10-10", "Выход"]);
});
