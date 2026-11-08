import test from "node:test";
import assert from "node:assert/strict";
import { lossDetailKey, lossDetailHref, readLossDetail } from "./features/losses/lossDetail.mjs";

test("every loss bar of both maps resolves to a detail page", () => {
  for (const [name, key] of [
    ["Номинальные потери НА", "nominal"], ["Потери из-за снижения КПД", "efficiency"],
    ["Отклонение от номинального КПД", "efficiency"], ["Потери на участке Насос–БГ", "pump_bg"],
    ["Потери в трубопроводах", "pipes"], ["Штуцирование нагнетательных скважин", "choke"],
    ["Номинальные", "nominal"], ["Потери КПД", "efficiency"], ["Дросселирование", "na_throttle"],
    ["Гидравл. насос→БГ", "hydraulic_bg"], ["Трение в трубопроводах", "friction"],
    ["Потери ЭД", "motor"], ["Потери насоса", "pump"], ["Трение в стволах скважин", "bore"],
  ]) assert.equal(lossDetailKey(name), key, name);
});

test("power totals are not losses and do not navigate", () => {
  for (const name of ["Гидравлическая мощность на БГ", "Полезная мощность", "Потреблённая мощность", "Полезная закачка"])
    assert.equal(lossDetailKey(name), null, name);
  assert.equal(lossDetailHref("Полезная мощность", "losses", "http://x/"), null);
});

test("detail link keeps the analysis context and remembers the map", () => {
  const href = lossDetailHref("Потери в трубопроводах", "losses", "http://x/?object=kns54an&aggregate=НА-1&day=2026-10-24#losses");
  const url = new URL(href, "http://x");
  assert.equal(url.hash, "#loss-detail");
  assert.equal(url.searchParams.get("object"), "kns54an");
  assert.equal(url.searchParams.get("day"), "2026-10-24");
  assert.deepEqual(readLossDetail(url.href), {loss: "pipes", from: "losses"});
  assert.deepEqual(readLossDetail("http://x/#loss-detail"), {loss: "", from: "losses"});
});

test("a loss detail keeps the inspection basis of its bar for sources, formulas and measures", async () => {
  const { lossInspection } = await import("./features/losses/lossDetail.mjs");
  const { inspections } = await import("./features/inspection/inspection.mjs");
  assert.equal(lossInspection("efficiency", inspections), "efficiency_loss");
  assert.equal(lossInspection("pump_bg", inspections), "throttle_loss");
  assert.equal(lossInspection("wear", inspections), "wear_loss");
  assert.equal(lossInspection("motor", inspections), "motor_loss");
  assert.equal(lossInspection("friction", inspections), undefined);
});
