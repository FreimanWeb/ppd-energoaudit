import { goToSection } from "./helpers";
import { selectDate } from "./helpers";
import {test, expect, type Page} from "@playwright/test";
test.afterEach(async ({page}) => {
  await page.unrouteAll({behavior: "wait"});
});
const incoming = "/?object=kns54an&aggregate=" + encodeURIComponent("НА-2") + "&day=2026-09-28&timestamp=2026-09-28T12:00:00&mode=analysis#machine-block";
async function selected(page: Page, aggregate: string, day: string, timestamp: string) {
  await expect(page.getByLabel("Агрегат", {exact: true})).toHaveValue(aggregate);
  await expect(page.getByLabel("Дата", {exact: true})).toBeEnabled();
  await expect(page.getByLabel("Дата", {exact: true})).toHaveAttribute("data-date", day);
  await expect(page.getByLabel("Момент измерения")).toHaveValue(timestamp);
  await expect.poll(() => new URL(page.url()).searchParams.get("timestamp")).toBe(timestamp);
}
test("shared URLs survive loading, reload, a new tab and browser history", async ({page, context}) => {
  await page.route("**/dates", async route => {
    const response = await route.fetch();
    await new Promise(resolve => setTimeout(resolve, 200));
    await route.fulfill({response});
  });
  await page.goto(incoming);
  await selected(page, "НА-2", "2026-09-28", "2026-09-28T12:00:00");
  await page.reload();
  await selected(page, "НА-2", "2026-09-28", "2026-09-28T12:00:00");
  const other = await context.newPage();
  await other.goto(page.url());
  await selected(other, "НА-2", "2026-09-28", "2026-09-28T12:00:00");
  await other.close();
  await goToSection(page, "sources");
  await page.getByLabel("Агрегат", {exact: true}).selectOption("НА-1");
  await selectDate(page, "2026-09-29");
  await page.getByLabel("Момент измерения").selectOption("2026-09-29T13:00:00");
  await selected(page, "НА-1", "2026-09-29", "2026-09-29T13:00:00");
  await goToSection(page, "formulas");
  await page.goBack();
  await selected(page, "НА-1", "2026-09-29", "2026-09-29T13:00:00");
  await page.goBack();
  await selected(page, "НА-2", "2026-09-28", "2026-09-28T12:00:00");
  await page.goForward();
  await selected(page, "НА-1", "2026-09-29", "2026-09-29T13:00:00");
});
test("navigation stays above independently scrolling analysis parameters", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 800});
  await page.goto("/#machine-block");
  await page.getByLabel("Объект", {exact: true}).selectOption("kns54an");
  await page.getByLabel("Агрегат", {exact: true}).selectOption("НА-1");
  await selectDate(page, "2026-09-29");
  await expect(page.getByLabel("Момент измерения")).toHaveValue("2026-09-29T23:30:00");
  const object = page.getByLabel("Объект", {exact: true});
  const before = await object.boundingBox();
  const nav = page.getByRole("navigation", {name: "Разделы энергоаудита"});
  expect(before!.y).toBeGreaterThan((await nav.boundingBox())!.y);
  await nav.locator('a[href="#sources"]').scrollIntoViewIfNeeded();
  expect((await object.boundingBox())!.y).toBe(before!.y);
  await page.getByLabel("Момент измерения").scrollIntoViewIfNeeded();
  await expect(page.getByLabel("Момент измерения")).toBeInViewport();
});
test("field trip links retain object and aggregate without a fabricated measurement", async ({page}) => {
  await page.goto(incoming);
  await selected(page, "НА-2", "2026-09-28", "2026-09-28T12:00:00");
  await page.getByLabel("Режим", {exact: true}).selectOption("field_trip");
  await expect.poll(() => new URL(page.url()).searchParams.get("mode")).toBe("field_trip");
  await page.reload();
  await expect(page.getByLabel("Режим", {exact: true})).toHaveValue("field_trip");
  await expect(page.getByLabel("Агрегат", {exact: true})).toHaveValue("НА-2");
  await expect(page.getByLabel("Дата", {exact: true})).toHaveCount(0);
  expect(new URL(page.url()).searchParams.has("timestamp")).toBe(false);
  expect(new URL(page.url()).searchParams.has("day")).toBe(false);
});

test("switching pumps and opening an area preserves the common measurement", async ({page}) => {
  await page.goto(incoming);
  await selected(page, "НА-2", "2026-09-28", "2026-09-28T12:00:00");
  await expect(page.getByLabel("Дата", {exact: true})).toBeEnabled();
  await expect(page.getByLabel("Момент измерения").locator("option:checked")).toBeEnabled();
  await page.getByLabel("Агрегат", {exact: true}).selectOption("НА-1");
  await selected(page, "НА-1", "2026-09-28", "2026-09-28T12:00:00");
  await goToSection(page, "machine-block");
  await page.getByLabel("Агрегат",{exact:true}).selectOption("НА-2");
  await selected(page, "НА-2", "2026-09-28", "2026-09-28T12:00:00");
  await page.reload();
  await selected(page, "НА-2", "2026-09-28", "2026-09-28T12:00:00");
});

test("a missing pump timestamp stays selected without substituting another calculation", async ({page}) => {
  await page.route("**/snapshots?*", async route => {
    const response = await route.fetch();
    const rows = await response.json();
    const isTarget = decodeURIComponent(route.request().url()).includes("/НА-1/");
    await route.fulfill({response, json: isTarget ? rows.filter((r: {timestamp: string}) => r.timestamp !== "2026-09-28T12:00:00") : rows});
  });
  const audits: string[] = [];
  page.on("request", request => {
    if (request.url().endsWith("/snapshot-audit")) audits.push(decodeURIComponent(request.url()));
  });
  await page.goto(incoming);
  await selected(page, "НА-2", "2026-09-28", "2026-09-28T12:00:00");
  await expect(page.getByLabel("Дата", {exact: true})).toBeEnabled();
  await expect(page.getByLabel("Момент измерения").locator("option:checked")).toBeEnabled();
  await page.getByLabel("Агрегат", {exact: true}).selectOption("НА-1");
  await selected(page, "НА-1", "2026-09-28", "2026-09-28T12:00:00");
  await expect(page.locator("main")).toContainText("На выбранное время нет пригодного снимка");
  expect(audits.some(url => url.includes("/НА-1/"))).toBe(false);
  await page.getByLabel("Момент измерения").selectOption("2026-09-28T13:00:00");
  await selected(page, "НА-1", "2026-09-28", "2026-09-28T13:00:00");
  await expect.poll(() => audits.some(url => url.includes("/НА-1/"))).toBe(true);
});

test("a missing pump date does not jump to the latest day", async ({page}) => {
  await page.route("**/dates", async route => {
    const response = await route.fetch();
    const body = await response.json();
    if (decodeURIComponent(route.request().url()).includes("/НА-1/")) body.dates = body.dates.filter((d: string) => d !== "2026-09-28");
    await route.fulfill({response, json: body});
  });
  await page.route("**/snapshots?day=2026-09-28", async route => {
    if (decodeURIComponent(route.request().url()).includes("/НА-1/")) await route.fulfill({json: []});
    else await route.continue();
  });
  await page.goto(incoming);
  await selected(page, "НА-2", "2026-09-28", "2026-09-28T12:00:00");
  await expect(page.getByLabel("Дата", {exact: true})).toBeEnabled();
  await expect(page.getByLabel("Момент измерения").locator("option:checked")).toBeEnabled();
  await page.getByLabel("Агрегат", {exact: true}).selectOption("НА-1");
  await selected(page, "НА-1", "2026-09-28", "2026-09-28T12:00:00");
  await expect(page.locator("main")).toContainText("За выбранную дату нет пригодных снимков");
  await expect(page.getByLabel("Дата", {exact: true})).toBeEnabled();
});
