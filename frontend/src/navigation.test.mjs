import test from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";

test("mode navigation retains the Streamlit view boundaries", async () => {
  assert.ok(
    existsSync(new URL("./navigation.mjs", import.meta.url)),
    "shared mode selector is missing",
  );
  const { pageForMode } = await import("./navigation.mjs");
  assert.equal(pageForMode("field_trip", "working-point"), "working-point");
  assert.equal(pageForMode("field_trip", "telemetry"), "overview");
  assert.equal(pageForMode("telemetry_view", "measures"), "telemetry");
  assert.equal(pageForMode("analysis", "crm-wells"), "crm-wells");
  assert.equal(pageForMode("analysis", "not-a-page"), "overview");
});

test("filters preserve empty selections as all and combined selections", async () => {
  assert.ok(
    existsSync(new URL("./navigation.mjs", import.meta.url)),
    "filter helper is missing",
  );
  const { filterObjects } = await import("./navigation.mjs");
  const objects = [
    { code: "a", water_type: "пресная", ngdu_name: "A" },
    { code: "b", water_type: "пластовая", ngdu_name: "B" },
  ];
  assert.deepEqual(filterObjects(objects, [], []), objects);
  assert.deepEqual(filterObjects(objects, ["пресная"], ["A"]), [objects[0]]);
  assert.deepEqual(filterObjects(objects, ["пресная"], ["B"]), objects);
});

test("calendar uses local ISO day strings, Monday weeks and leap years", async () => {
  assert.ok(
    existsSync(new URL("./navigation.mjs", import.meta.url)),
    "calendar helper is missing",
  );
  const { monthDays } = await import("./navigation.mjs");
  const days = monthDays("2024-02");
  assert.equal(days[3], "2024-02-01");
  assert.equal(days.filter(Boolean).length, 29);
  assert.equal(days.length % 7, 0);
  assert.equal(monthDays("2025-02").filter(Boolean).length, 28);
});
