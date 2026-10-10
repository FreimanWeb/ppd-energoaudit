import test from "node:test";
import assert from "node:assert/strict";
import * as metrics from "./shared/metrics/metricAssessment.mjs";

test("metric comparison follows the physical direction and preserves zero", () => {
  assert.equal(typeof metrics.metricAssessment, "function");
  const assess = metrics.metricAssessment;
  assert.equal(assess(4, 3, "higher").tone, "bad");
  assert.equal(assess(2, 3, "higher").tone, "good");
  assert.equal(assess(.6, .8, "lower").tone, "bad");
  assert.equal(assess(.9, .8, "lower").tone, "good");
  assert.equal(assess(3, 3, "higher").tone, "good");
  assert.equal(assess(0, 0, "higher").tone, "good");
  assert.equal(assess(1, 0, "higher").tone, "bad");
  assert.equal(assess(null, 3, "higher").tone, "neutral");
  assert.equal(assess(3, null, "higher").tone, "neutral");
  assert.equal(assess(NaN, 3, "higher").tone, "neutral");
  assert.equal(assess(.9, .8, "lower", false).tone, "neutral");
  assert.equal(assess(1.1, null, "lower", false, true).tone, "bad");
  assert.equal(assess(-.1, .8, "lower", true, true).tone, "bad");
});
