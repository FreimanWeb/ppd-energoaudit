import test from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";

test("mode navigation retains the Streamlit view boundaries", async () => {
  assert.ok(
    existsSync(new URL("./app/navigation.mjs", import.meta.url)),
    "shared mode selector is missing",
  );
  const { pageForMode } = await import("./app/navigation.mjs");
  assert.equal(pageForMode("field_trip", "working-point"), "working-point");
  assert.equal(pageForMode("field_trip", "telemetry"), "overview");
  assert.equal(pageForMode("telemetry_view", "measures"), "telemetry");
  assert.equal(pageForMode("analysis", "crm-wells"), "crm-wells");
  assert.equal(pageForMode("analysis", "not-a-page"), "overview");
});

test("monitoring starts with all objects and opens object history without requiring a snapshot", async () => {
  const nav = await import("./app/navigation.mjs");
  assert.equal(typeof nav.initialPage, "function");
  assert.equal(nav.initialPage("http://localhost/"), "portfolio");
  assert.equal(nav.initialPage("http://localhost/?object=kns54an"), "timeline");
  assert.equal(nav.initialPage("http://localhost/?mode=field_trip"), "overview");
  assert.equal(nav.initialPage("http://localhost/?mode=telemetry_view"), "telemetry");
  assert.equal(nav.initialPage("http://localhost/?object=kns54an#snapshot"), "snapshot");
  assert.equal(nav.pageForMode("analysis", "timeline"), "timeline");
  assert.equal(nav.pageForMode("field_trip", "portfolio"), "portfolio");
});

test("filters preserve empty selections as all and combined selections", async () => {
  assert.ok(
    existsSync(new URL("./app/navigation.mjs", import.meta.url)),
    "filter helper is missing",
  );
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
  assert.ok(
    existsSync(new URL("./app/navigation.mjs", import.meta.url)),
    "calendar helper is missing",
  );
  const { monthDays } = await import("./app/navigation.mjs");
  const days = monthDays("2024-02");
  assert.equal(days[3], "2024-02-01");
  assert.equal(days.filter(Boolean).length, 29);
  assert.equal(days.length % 7, 0);
  assert.equal(monthDays("2025-02").filter(Boolean).length, 28);
});


test("sidebar sections preserve every route with a distinct icon", async () => {
  const { navigationSections, pages } = await import("./app/navigation.mjs");
  assert.ok(navigationSections, "sectioned navigation is missing");
  assert.deepEqual(navigationSections.map(s => s.label), ["Все объекты","Обзор","Машинный блок","Трубопроводы","Скважины","Мероприятия","Данные и методика"]);
  assert.equal(pages.length, 20);
  assert.equal(new Set(pages.map(p => p.id)).size, 20);
  assert.equal(new Set(pages.map(p => p.icon)).size, 20);
  assert.equal(pages.some(p => p.id === "scheme"), false);
  assert.deepEqual(navigationSections.flatMap(s => s.pages), pages);
});


test("analysis context round-trips Cyrillic aggregates and keeps the page and unrelated query", async () => {
  const nav = await import("./app/navigation.mjs");
  assert.equal(typeof nav.analysisContextURL, "function");
  const context = {object: "kns54an", aggregate: "НА-2", day: "2026-09-28", timestamp: "2026-09-28T12:00:00", mode: "analysis"};
  const href = nav.analysisContextURL("http://localhost/?keep=1#scheme", context);
  assert.deepEqual(nav.readAnalysisContext(href), context);
  assert.equal(new URL(href).hash, "#scheme");
  assert.equal(new URL(href).searchParams.get("keep"), "1");
});

test("source modes omit irrelevant measurement parameters and unknown modes fall back", async () => {
  const nav = await import("./app/navigation.mjs");
  assert.equal(typeof nav.readAnalysisContext, "function");
  const original = {object: "kns54an", aggregate: "НА-2", day: "2026-09-28", timestamp: "2026-09-28T12:00:00", mode: "field_trip"};
  const trip = new URL(nav.analysisContextURL("http://localhost/", original));
  assert.equal(trip.searchParams.has("day"), false);
  assert.equal(trip.searchParams.has("timestamp"), false);
  const viewer = new URL(nav.analysisContextURL(trip.href, {...original, mode: "telemetry_view"}));
  assert.equal(viewer.searchParams.get("day"), original.day);
  assert.equal(viewer.searchParams.has("timestamp"), false);
  assert.equal(nav.readAnalysisContext("http://localhost/?mode=unknown").mode, "analysis");
});


test("operator list keeps three real objects and one explicit demo", async () => {
  const {operatorObjects,pageForMode} = await import("./app/navigation.mjs");
  assert.deepEqual(operatorObjects(["knsopu","kns54an","kns97pren","demo-ppd","kns10bn","dns7"].map(code => ({code}))).map(o => o.code),["knsopu","kns54an","kns97pren","demo-ppd"]);
  for (const page of ["machine-block","pipelines","wells"]) assert.equal(pageForMode("field_trip",page),page);
});

test('overview stays station-wide and injection forecasting belongs to wells',async()=>{
 const {navigationSections,pageForMode}=await import('./app/navigation.mjs');
 assert.deepEqual(navigationSections.find(section=>section.root==='timeline').pages.map(page=>page.id),['timeline','overview','losses']);
 assert.deepEqual(navigationSections.find(section=>section.root==='pipelines').pages.map(page=>page.id),['pipelines','network','network-scenario']);
 assert.equal(pageForMode('field_trip','network-scenario'),'network-scenario');
 assert.ok(navigationSections.find(section=>section.root==='wells').pages.some(page=>page.id==='forecast'));
});
