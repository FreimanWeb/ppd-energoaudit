import test from "node:test";
import assert from "node:assert/strict";
import * as data from "./features/overview/dashboardData.mjs";
const fixture = {
  source: "field_trip",
  snapshot: null,
  quality: { status: "ready" },
  scope: { annual_runtime_hours: 8000, annual_runtime_is_assumed: false },
  audit: { metrics: { eta_unit: 0.65, sec_fact_kwh_m3: 3 } },
  regime: { p_in: 1, p_out: 10, w: 100, t: 24 },
  annual_summary: { efficiency_money_krub: 100, efficiency_energy_kwh: 200 },
};
test("field-trip label never manufactures a telemetry timestamp", () => {
  assert.equal(typeof data.dashboardData, "function");
  const view = data.dashboardData(fixture);
  assert.equal(view.timestamp, null);
  assert.equal(view.source, "Выездной замер (YAML)");
  assert.equal(view.annual.efficiency_money_krub, 100);
});
test("unfit mode cannot expose economic totals or losses", () => {
  assert.equal(typeof data.dashboardData, "function");
  const view = data.dashboardData({
    ...fixture,
    quality: { status: "unfit" },
    losses: [{ annual_rub: 1 }],
  });
  assert.equal(view.annual, null);
  assert.deepEqual(view.losses, []);
});
