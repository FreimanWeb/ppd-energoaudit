import test from "node:test";
import assert from "node:assert/strict";
import {journalPatch, normalizeEquipmentTime, parameterDifferences, parseEquipmentNumber, sameParameterValue} from "../features/manual/journalDraft.mjs";

test("editing one characteristic does not republish the rest of the equipment", () => {
  const before = {"pump.h_nom": 100, "pump.eta_nom": 0.8, "pump.model": "Насос"};
  assert.deepEqual(journalPatch(before, {...before, "pump.h_nom": 120}, "repair"), {"pump.h_nom": 120});
  assert.deepEqual(journalPatch(before, {...before}, "passport"), {});
});

test("a formatting change or reverted edit does not create an observation", () => {
  const before = {"pump.h_nom": 100};
  assert.deepEqual(journalPatch(before, {"pump.h_nom": parseEquipmentNumber("100,00")}, "repair"), {});
  assert.deepEqual(journalPatch(before, {"pump.h_nom": parseEquipmentNumber(" 1e2 ")}, "inspection"), {});
});

test("clearing a known characteristic records unknown, not zero or an omitted field", () => {
  assert.deepEqual(journalPatch({"pump.eta_nom": 0.8}, {"pump.eta_nom": parseEquipmentNumber(" ")}, "repair"), {"pump.eta_nom": null});
  assert.deepEqual(journalPatch({"pump.eta_nom": null}, {"pump.eta_nom": null}, "repair"), {});
});

test("an explicitly known false is distinct from an unknown equipment flag", () => {
  assert.deepEqual(journalPatch({vfd: null}, {vfd: false}, "inspection"), {vfd: false});
  assert.deepEqual(journalPatch({vfd: false}, {vfd: false}, "inspection"), {});
  assert.deepEqual(journalPatch({"motor.cos_phi": 0.8}, {"motor.cos_phi": 0}, "repair"), {"motor.cos_phi": 0});
});

test("unchanged curves and reordered source properties are not new evidence", () => {
  const before = {"pump.curve_qh": [[0, 120], [100, 100]], "pump.curve_source": {reference: "Паспорт", verified: false}};
  const after = {"pump.curve_qh": [[0, 120], [100, 100]], "pump.curve_source": {verified: false, reference: "Паспорт"}};
  assert.deepEqual(journalPatch(before, after, "repair"), {});
  after["pump.curve_qh"][1][1] = 90;
  assert.deepEqual(parameterDifferences(before, after), [{key: "pump.curve_qh", before: [[0, 120], [100, 100]], after: [[0, 120], [100, 90]]}]);
});

test("removing a curve or its source preserves the explicit clearing operation", () => {
  assert.deepEqual(journalPatch({"pump.curve_qh": [[100, 120]], "pump.curve_source": {reference: "Паспорт"}}, {"pump.curve_qh": [], "pump.curve_source": null}, "repair"), {"pump.curve_qh": [], "pump.curve_source": null});
});

test("correction retains the original declared fields even for a date-only correction", () => {
  const original = {"pump.h_nom": 100, "pump.eta_nom": null};
  assert.deepEqual(journalPatch(original, {...original}, "correction"), original);
  assert.deepEqual(parameterDifferences(original, {...original}), []);
  assert.deepEqual(journalPatch(original, {...original, "pump.h_nom": 120}, "correction"), {"pump.h_nom": 120, "pump.eta_nom": null});
});

test("replacement explicitly declares a new unit even when its characteristics coincide", () => {
  const previous = {"pump.model": "Насос", "pump.kind": "центробежный", "pump.h_nom": 100};
  assert.deepEqual(journalPatch(previous, {...previous, "pump.eta_nom": null, "pump.curve_qh": []}, "replacement"), previous);
  assert.deepEqual(journalPatch({vfd: true}, {vfd: false}, "replacement"), {vfd: false});
});

test("unknown replacement characteristics are omitted rather than confirmed as defaults", () => {
  assert.deepEqual(journalPatch({"motor.model": "Старый", "motor.synchronous": true}, {"motor.model": "Новый", "motor.synchronous": null, "motor.eta_nom": null}, "replacement"), {"motor.model": "Новый"});
});

test("decimal input does not turn missing or invalid numbers into zero", () => {
  assert.equal(parseEquipmentNumber("0,85"), 0.85);
  assert.equal(parseEquipmentNumber(""), null);
  assert.ok(Number.isNaN(parseEquipmentNumber("не число")));
  assert.equal(parseEquipmentNumber("-0,5"), -0.5);
});

test("local action time compares equal across input precision without timezone conversion", () => {
  assert.equal(normalizeEquipmentTime("2026-07-24T14:40"), normalizeEquipmentTime("2026-07-24T14:40:00.000000"));
  assert.equal(normalizeEquipmentTime("2026-07-24"), "2026-07-24T00:00:00");
  assert.equal(normalizeEquipmentTime("2026-07-24T14:40:00.120000"), "2026-07-24T14:40:00.12");
  assert.notEqual(normalizeEquipmentTime("2026-07-24T14:40:00.001"), normalizeEquipmentTime("2026-07-24T14:40:00.002"));
});

test("source applicability changes are not hidden by property-order normalization", () => {
  assert.equal(sameParameterValue({verified: false, model: "A"}, {model: "B", verified: false}), false);
});
