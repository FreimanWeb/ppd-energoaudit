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
test("field-trip results cannot inherit a telemetry timestamp", () => {
  const view = data.dashboardData({
    ...fixture,
    snapshot: { timestamp: "2026-10-29T10:00:00" },
  });
  assert.equal(view.timestamp, null);
});
test("regime fallback is never exposed as measured daily SEC", () => {
  const view = data.dashboardData({
    ...fixture,
    scope: { ...fixture.scope, daily_kpi_is_fact: false },
  });
  assert.equal(view.dailySec, null);
  assert.equal(view.regimeSec, 3);
});
test("daily SEC is not reused as a selected-regime calculation", () => {
  const view = data.dashboardData({
    ...fixture,
    scope: { ...fixture.scope, daily_kpi_is_fact: true },
  });
  assert.equal(view.dailySec, 3);
  assert.equal(view.regimeSec, null);
});
test("zero measured energy remains a daily measurement", () => {
  const view = data.dashboardData({
    ...fixture,
    scope: { ...fixture.scope, daily_kpi_is_fact: true },
    audit: { metrics: { sec_fact_kwh_m3: 0 } },
    regime: { ...fixture.regime, w: 0, q_day: 50 },
  });
  assert.equal(view.dailySec, 0);
});
test("unfit mode cannot expose economic totals or losses", () => {
  const daily = { ...fixture.scope, daily_kpi_is_fact: true };
  const view = data.dashboardData({
    ...fixture,
    scope: daily,
    quality: { status: "unfit" },
    losses: [{ annual_rub: 1 }],
  });
  assert.equal(view.annual, null);
  assert.deepEqual(view.losses, []);
  assert.equal(view.dailySec, 3);
});
