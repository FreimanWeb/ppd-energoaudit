import test from "node:test";
import assert from "node:assert/strict";

test("mode navigation enforces analysis, field-trip and telemetry boundaries", async () => {
  const { pageForMode } = await import("./app/navigation.mjs");
  assert.equal(pageForMode("field_trip", "working-point"), "working-point");
  assert.equal(pageForMode("field_trip", "telemetry"), "overview");
  assert.equal(pageForMode("telemetry_view", "measures"), "telemetry");
  assert.equal(pageForMode("analysis", "crm-wells"), "crm-wells");
  assert.equal(pageForMode("analysis", "not-a-page"), "overview");
});

test("monitoring starts with all objects and opens object history without requiring a snapshot", async () => {
  const nav = await import("./app/navigation.mjs");
  assert.equal(nav.initialPage("http://localhost/"), "portfolio");
  assert.equal(nav.initialPage("http://localhost/?object=kns54an"), "timeline");
  assert.equal(nav.initialPage("http://localhost/?mode=field_trip"), "overview");
  assert.equal(nav.initialPage("http://localhost/?mode=telemetry_view"), "telemetry");
  assert.equal(nav.initialPage("http://localhost/?object=kns54an#snapshot"), "snapshot");
  assert.equal(nav.pageForMode("analysis", "timeline"), "timeline");
  assert.equal(nav.pageForMode("field_trip", "portfolio"), "portfolio");
});

test("filters preserve empty selections as all and combined selections", async () => {
  const { filterObjects } = await import("./app/navigation.mjs");
  const objects = [
    { code: "a", water_type: "пресная", ngdu_name: "A" },
    { code: "b", water_type: "пластовая", ngdu_name: "B" },
  ];
  assert.deepEqual(filterObjects(objects, [], []), objects);
  assert.deepEqual(filterObjects(objects, ["пресная"], ["A"]), [objects[0]]);
  assert.deepEqual(filterObjects(objects, ["пресная"], ["B"]), []);
});

test("calendar uses local ISO day strings, Monday weeks and leap years", async () => {
  const { monthDays } = await import("./app/navigation.mjs");
  const days = monthDays("2024-02");
  assert.equal(days[3], "2024-02-01");
  assert.equal(days.filter(Boolean).length, 29);
  assert.equal(days.length % 7, 0);
  assert.equal(monthDays("2025-02").filter(Boolean).length, 28);
});

test("analysis context round-trips Cyrillic aggregates and keeps the page and unrelated query", async () => {
  const nav = await import("./app/navigation.mjs");
  const context = {object: "kns54an", aggregate: "НА-2", day: "2026-09-28", timestamp: "2026-09-28T12:00:00", mode: "analysis", measurement: ""};
  const href = nav.analysisContextURL("http://localhost/?keep=1&measurement=7#scheme", context);
  assert.deepEqual(nav.readAnalysisContext(href), context);
  assert.equal(new URL(href).searchParams.has("measurement"), false);
  assert.equal(new URL(href).hash, "#scheme");
  assert.equal(new URL(href).searchParams.get("keep"), "1");
});

test("source modes omit irrelevant measurement parameters and unknown modes fall back", async () => {
  const nav = await import("./app/navigation.mjs");
  const original = {object: "kns54an", aggregate: "НА-2", day: "2026-09-28", timestamp: "2026-09-28T12:00:00", mode: "field_trip"};
  const trip = new URL(nav.analysisContextURL("http://localhost/", original));
  assert.equal(trip.searchParams.has("day"), false);
  assert.equal(trip.searchParams.has("timestamp"), false);
  const viewer = new URL(nav.analysisContextURL(trip.href, {...original, mode: "telemetry_view"}));
  assert.equal(viewer.searchParams.get("day"), original.day);
  assert.equal(viewer.searchParams.has("timestamp"), false);
  assert.equal(nav.readAnalysisContext("http://localhost/?mode=unknown").mode, "analysis");
});



test("field-trip mode keeps machine, pipeline and well pages", async () => {
  const {pageForMode} = await import("./app/navigation.mjs");
  for (const page of ["machine-block","machine-losses","pipelines","wells"]) assert.equal(pageForMode("field_trip",page),page);
});

test('overview stays station-wide and injection forecasting belongs to wells',async()=>{
 const {navigationSections,pageForMode}=await import('./app/navigation.mjs');
 assert.deepEqual(navigationSections.find(section=>section.root==='timeline').pages.map(page=>page.id),['timeline','overview','losses','loss-detail']);
 assert.ok(navigationSections.find(section=>section.root==='timeline').pages.find(page=>page.id==='loss-detail').hidden);
 assert.deepEqual(navigationSections.find(section=>section.root==='pipelines').pages.map(page=>page.id),['pipelines','network','network-scenario']);
 assert.equal(pageForMode('field_trip','network-scenario'),'network-scenario');
 assert.ok(navigationSections.find(section=>section.root==='wells').pages.some(page=>page.id==='forecast'));
});


test('machine block separates indicators, loss map, working point and recommendations',async()=>{
 const {navigationSections,pageForMode}=await import('./app/navigation.mjs');
 assert.deepEqual(navigationSections.find(section=>section.root==='machine-block').pages.map(page=>[page.id,page.label]),[
  ['machine-block','Показатели'],['machine-losses','Карта потерь'],['working-point','Рабочая точка'],['recommendations','Рекомендации'],
 ]);
 assert.equal(pageForMode('analysis','machine-losses'),'machine-losses');
 assert.equal(pageForMode('field_trip','machine-losses'),'machine-losses');
});

test("equipment edits return to the exact loss, regime and decomposition after reload", async () => {
  const { equipmentJournalHref, equipmentReturnHref } = await import("./app/navigation.mjs");
  const origin = "http://localhost/?object=knsopu&aggregate=%D0%9D%D0%90-1&mode=analysis&day=2026-09-29&timestamp=2026-09-29T12%3A00%3A00&inspect=pump_loss&decomposition=equipment#formulas";
  const journal = new URL(equipmentJournalHref("motor.eta_nom", origin), origin);
  assert.equal(journal.hash, "#equipment-journal");
  assert.equal(journal.searchParams.get("focus"), "motor.eta_nom");
  assert.equal(equipmentReturnHref(journal.href), new URL(origin).pathname + new URL(origin).search + "#formulas");
});

test("equipment return never switches context or navigates to an external or recursive destination", async () => {
  const { equipmentJournalHref, equipmentReturnHref } = await import("./app/navigation.mjs");
  const origin = "http://localhost/?object=knsopu&aggregate=NA-1&mode=field_trip&measurement=7&inspect=pump_loss#machine-losses";
  const journal = new URL(equipmentJournalHref("motor.eta_nom", origin), origin);
  for (const [key, value] of [["object", "kns54an"], ["aggregate", "NA-2"], ["measurement", "8"], ["mode", "analysis"]]) {
    const changed = new URL(journal);
    changed.searchParams.set(key, value);
    assert.equal(equipmentReturnHref(changed.href), null);
  }
  for (const destination of ["https://example.com/#machine-losses", "/other#machine-losses", "/#equipment-journal", "http://[invalid"]) {
    journal.searchParams.set("return_to", destination);
    assert.equal(equipmentReturnHref(journal.href), null);
  }
});
