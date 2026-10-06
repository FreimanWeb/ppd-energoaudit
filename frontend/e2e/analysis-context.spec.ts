import {test, expect, type Page} from "@playwright/test";
const incoming = "/?object=kns54an&aggregate=" + encodeURIComponent("НА-2") + "&day=2026-09-28&timestamp=2026-09-28T12:00:00&mode=analysis#scheme";
async function selected(page: Page, aggregate: string, day: string, timestamp: string) {
  await expect(page.getByLabel("Агрегат", {exact: true})).toHaveValue(aggregate);
  await expect(page.getByLabel("Дата", {exact: true})).toHaveValue(day);
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
  await page.locator('nav a[href="#sources"]').click();
  await page.getByLabel("Агрегат", {exact: true}).selectOption("НА-1");
  await page.getByLabel("Дата", {exact: true}).selectOption("2026-09-29");
  await page.getByLabel("Момент измерения").selectOption("2026-09-29T13:00:00");
  await selected(page, "НА-1", "2026-09-29", "2026-09-29T13:00:00");
  await page.locator('nav a[href="#formulas"]').click();
  await page.goBack();
  await selected(page, "НА-1", "2026-09-29", "2026-09-29T13:00:00");
  await page.goBack();
  await selected(page, "НА-2", "2026-09-28", "2026-09-28T12:00:00");
  await page.goForward();
  await selected(page, "НА-1", "2026-09-29", "2026-09-29T13:00:00");
});
test("analysis parameters stay above independently scrolling navigation", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 800});
  await page.goto("/");
  await page.getByLabel("Объект", {exact: true}).selectOption("kns54an");
  await page.getByLabel("Агрегат", {exact: true}).selectOption("НА-1");
  await page.getByLabel("Дата", {exact: true}).selectOption("2026-09-29");
  await expect(page.getByLabel("Момент измерения")).toHaveValue("2026-09-29T23:30:00");
  const object = page.getByLabel("Объект", {exact: true});
  const before = await object.boundingBox();
  const nav = page.getByRole("navigation", {name: "Разделы энергоаудита"});
  expect(before!.y).toBeLessThan((await nav.boundingBox())!.y);
  await nav.locator('a[href="#onboarding"]').scrollIntoViewIfNeeded();
  expect((await object.boundingBox())!.y).toBe(before!.y);
  expect((await page.getByLabel("Момент измерения").boundingBox())!.y).toBeLessThan(700);
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
