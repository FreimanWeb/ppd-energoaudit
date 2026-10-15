import assert from "node:assert/strict";
import test from "node:test";
import { networkMeasures } from "./features/losses/networkScenario.mjs";

const measures = [
  { id: "pipes", loss_name: "Трубы", saving_kw: 3 },
  { id: "head", loss_name: "Штуцеры", saving_kw: 9 },
  { id: "invalid", loss_name: "Трубы", saving_kw: NaN },
  { id: "zero", loss_name: "Трубы", saving_kw: 0 },
];
test("network measures rank positive finite savings without changing source order", () => {
  assert.deepEqual(networkMeasures("scenario", measures).map(row => row.id), ["head", "pipes"]);
  assert.equal(measures[0].id, "pipes");
});
test("network measures match the selected chain component", () => {
  assert.deepEqual(networkMeasures("scenario", measures, "Трубы").map(row => row.id), ["pipes"]);
  assert.deepEqual(networkMeasures("scenario", measures, "Полезная мощность"), []);
});
test("unavailable and infeasible balances expose no savings", () => {
  assert.deepEqual(networkMeasures("infeasible", measures), []);
  assert.deepEqual(networkMeasures("unavailable", measures), []);
});
