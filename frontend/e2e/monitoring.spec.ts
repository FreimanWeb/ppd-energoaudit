import { test, expect } from "@playwright/test";
import { selectDate } from "./helpers";

test("home shows every object and opens history without selecting a measurement", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Состояние объектов", exact: true })).toBeVisible();
  await expect(page.getByLabel("Момент измерения")).toHaveCount(0);
  await expect(page.locator(".app-sidebar, .sidebar-toggle")).toHaveCount(0);
  expect(await page.locator("main").evaluate(element => element.getBoundingClientRect().x)).toBe(0);
  expect(new URL(page.url()).searchParams.has("timestamp")).toBe(false);
  const cards = page.locator(".portfolio-card");
  await expect(cards).toHaveCount(4);
  await page.getByRole("button", { name: /КНС-54/ }).click();
  await expect.poll(() => new URL(page.url()).hash).toBe("#timeline");
  await expect(page.locator(".app-sidebar")).toBeVisible();
  await expect(page.locator("main")).toContainText("История");
  await expect(page.getByLabel("Момент измерения")).toBeVisible();
  expect(new URL(page.url()).searchParams.has("timestamp")).toBe(false);
  await page.reload();
  await expect(page.locator("main")).toContainText("История");
  await page.getByRole("link", { name: "Перейти ко всем объектам", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Состояние объектов", exact: true })).toBeVisible();
  await page.goBack();
  await expect.poll(() => new URL(page.url()).hash).toBe("#timeline");
});

test("monitoring stays usable on a narrow screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator(".app-sidebar, .sidebar-toggle")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Состояние объектов", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: /КНС-54/ }).click();
  await expect(page.locator("main")).toContainText("История");
  await expect(page.getByRole("button", { name: "Открыть боковую панель" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("portfolio filters open above the page without shifting cards", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".portfolio-card").first()).toBeVisible();
  const grid = page.locator(".portfolio-grid");
  const top = (await grid.boundingBox())!.y;
  const filters = page.locator(".portfolio-toolbar .object-filter");
  for (const index of [0, 1]) {
    const filter = filters.nth(index);
    await filter.locator("summary").click();
    await expect(filter).toHaveAttribute("open", "");
    await expect(filter.locator(":scope > div")).toBeVisible();
    expect((await grid.boundingBox())!.y).toBe(top);
    await page.keyboard.press("Escape");
    await expect(filter).not.toHaveAttribute("open", "");
  }
  await filters.first().locator("summary").click();
  await page.getByRole("heading", {name:"Состояние объектов", exact:true}).click();
  await expect(filters.first()).not.toHaveAttribute("open", "");
  await page.setViewportSize({width:390,height:844});
  await filters.last().locator("summary").click();
  const popup = (await filters.last().locator(":scope > div").boundingBox())!;
  expect(popup.x).toBeGreaterThanOrEqual(0);
  expect(popup.x + popup.width).toBeLessThanOrEqual(390);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("portfolio filter fields show clear labels and selected values", async ({ page }) => {
  await page.goto("/");
  const filter = page.locator(".portfolio-toolbar .object-filter").last();
  const trigger = filter.locator("summary");
  await expect(trigger.locator(".object-filter-title")).toHaveText("Тип воды");
  await expect(trigger.locator(".object-filter-value")).toHaveText("Все");
  await expect(trigger.locator("svg")).toBeVisible();
  await trigger.click();
  await page.getByLabel("Тип воды: пресная", {exact:true}).check();
  await expect(trigger.locator(".object-filter-value")).toHaveText("пресная");
  await expect(filter).toHaveAttribute("data-active", "true");
  await page.getByLabel("Тип воды: агрессивная", {exact:true}).check();
  await expect(trigger.locator(".object-filter-value")).toHaveText("Выбрано: 2");
  await page.getByLabel("Тип воды: пресная", {exact:true}).uncheck();
  await page.getByLabel("Тип воды: агрессивная", {exact:true}).uncheck();
  await expect(trigger.locator(".object-filter-value")).toHaveText("Все");
  await expect(filter).toHaveAttribute("data-active", "false");
});

test("portfolio offers up to six months of full-width charts in wide cards", async ({ page }) => {
  await page.setViewportSize({width: 1600, height: 1000});
  await page.goto("/");
  await selectDate(page, "2026-10-01", "Дата окончания графиков");
  const card = page.locator(".portfolio-card").filter({has: page.getByRole("heading", {name: "КНС-54", exact: true})});
  await expect(card.locator(".portfolio-sparkline circle")).toHaveCount(30);
  await expect(page.getByLabel("Период графиков")).toHaveValue("30");
  const svg = card.locator(".portfolio-sparkline");
  const graphWidth = (await svg.boundingBox())!.width;
  expect((await svg.locator(".portfolio-sparkline-baseline").boundingBox())!.width / graphWidth).toBeGreaterThan(0.9);
  const dot = (await svg.locator("circle").first().boundingBox())!;
  expect(dot.width).toBeCloseTo(5, 1);
  expect(dot.height).toBeCloseTo(5, 1);
  await page.getByLabel("Период графиков").selectOption("180");
  await expect(card.locator(".portfolio-sparkline circle")).toHaveCount(93);
  await page.getByLabel("Период графиков").selectOption("90");
  await expect(card.locator(".portfolio-sparkline circle")).toHaveCount(90);
  await page.getByLabel("Период графиков").selectOption("7");
  await expect(card.locator(".portfolio-sparkline circle")).toHaveCount(7);
  await expect(card.locator(".portfolio-history-range time").first()).toHaveAttribute("datetime", "2026-09-25");
  await page.getByLabel("Период графиков").selectOption("1");
  await expect(card.locator(".portfolio-sparkline circle")).toHaveCount(1);
  const cards = page.locator(".portfolio-card");
  const first = (await cards.nth(0).boundingBox())!;
  const second = (await cards.nth(1).boundingBox())!;
  const third = (await cards.nth(2).boundingBox())!;
  expect(first.width).toBeGreaterThan(700);
  expect(first.y).toBe(second.y);
  expect(third.x).toBe(first.x);
  expect(third.y).toBeGreaterThan(first.y);
});

test("portfolio tooltip stays outside clipping containers and appears only while hovering", async ({ page }) => {
  await page.goto("/");
  await selectDate(page, "2026-10-01", "Дата окончания графиков");
  const card = page.locator(".portfolio-card").filter({has: page.getByRole("heading", {name: "КНС-54", exact: true})});
  const point = card.locator(".portfolio-sparkline circle").first();
  await point.scrollIntoViewIfNeeded();
  await point.evaluate(element => window.scrollBy(0, element.getBoundingClientRect().top - 24));
  const dot = (await point.boundingBox())!;
  const graph = (await card.locator(".portfolio-sparkline").boundingBox())!;
  await page.mouse.move(dot.x + dot.width / 2, graph.y + graph.height - 6);
  const tooltip = page.locator(".portfolio-point-tooltip");
  await expect(tooltip).toBeVisible();
  await expect(tooltip).toContainText("02.09.2026");
  await expect(tooltip).toContainText("5 кВт·ч/м³");
  expect(await tooltip.evaluate(element => element.parentElement === document.body)).toBe(true);
  const bounds = (await tooltip.boundingBox())!;
  expect(bounds.y).toBeGreaterThanOrEqual(12);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(page.viewportSize()!.height - 12);
  await page.mouse.move(0, 0);
  await expect(tooltip).toHaveCount(0);
  await point.evaluate(element => element.setAttribute("tabindex", "0"));
  await point.focus();
  await expect(tooltip).toHaveCount(0);
  await point.click();
  await expect(tooltip).toBeVisible();
  await page.mouse.move(0, 0);
  await expect(tooltip).toHaveCount(0);
  await page.setViewportSize({width: 390, height: 844});
  await point.hover();
  await expect(tooltip).toBeVisible();
  const mobile = (await tooltip.boundingBox())!;
  expect(mobile.x).toBeGreaterThanOrEqual(12);
  expect(mobile.x + mobile.width).toBeLessThanOrEqual(378);
  await page.getByLabel("Период графиков").selectOption("7");
  await expect(tooltip).toHaveCount(0);
});

test("portfolio defaults to today and uses a common selected end date for all charts", async ({ page }) => {
  await page.goto("/");
  const today = await page.evaluate(() => new Intl.DateTimeFormat("sv-SE", {timeZone:"Europe/Moscow"}).format(new Date()));
  const picker = page.getByLabel("Дата окончания графиков");
  await expect(picker).toHaveAttribute("data-date",today);
  await selectDate(page, "2026-10-15", "Дата окончания графиков");
  const card = page.locator(".portfolio-card").filter({has:page.getByRole("heading", {name:"КНС-54",exact:true})});
  await expect(card.locator(".portfolio-history-range time").last()).toHaveAttribute("datetime", "2026-10-15");
  await expect(card.locator(".portfolio-sparkline circle")).toHaveCount(16);
  const svg = card.locator(".portfolio-sparkline");
  const lastX = Number(await svg.locator("circle").last().getAttribute("cx"));
  expect(lastX / (await svg.boundingBox())!.width).toBeLessThan(0.6);
  await selectDate(page, "2026-07-07", "Дата окончания графиков");
  await page.getByLabel("Период графиков").selectOption("7");
  await expect(card.locator(".portfolio-sparkline circle")).toHaveCount(7);
  await expect(card.locator(".portfolio-history-range time").last()).toHaveAttribute("datetime", "2026-07-07");
});

test("legacy filters cannot replace the object opened from a monitoring card", async ({ page }) => {
  await page.goto("/?object=kns54an&aggregate=НА-1&day=2026-09-29#overview");
  await page.locator(".object-filter").filter({ hasText: "Тип воды" }).locator("summary").click();
  await page.getByLabel("Тип воды: пресная", { exact: true }).check();
  await page.getByRole("link", { name: "Все объекты", exact: true }).click();
  await page.getByRole("button", { name: /Открыть историю: КНС-54/ }).click();
  await expect(page.getByLabel("Объект", { exact: true })).toHaveValue("kns54an");
  await expect(page.locator(".page-heading h1")).toContainText("КНС-54");
  await page.getByRole("link", { name: "Схема и участки", exact: true }).click();
  await expect(page.getByLabel("Объект", { exact: true })).toHaveValue("kns54an");
});

test("changing equipment cancels a pending analysis time lookup", async ({ page }) => {
  await page.goto("/?object=kns54an&aggregate=НА-1&day=2026-09-29#timeline");
  await expect(page.getByLabel("Момент измерения",{exact:true})).toBeEnabled();
  let release!: () => void, started!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const pending = new Promise<void>(resolve => { started = resolve; });
  await page.route("**/aggregates/**/snapshots?day=2026-09-28", async route => {
    const response = await route.fetch();
    started();
    await gate;
    await route.fulfill({ response });
  });
  try {
    await selectDate(page,"2026-09-28");
    await pending;
    await page.getByLabel("Агрегат",{exact:true}).selectOption("НА-2");
  } finally {
    release();
  }
  await page.waitForLoadState("networkidle");
  await expect(page.getByLabel("Агрегат",{exact:true})).toHaveValue("НА-2");
  expect(new URL(page.url()).hash).toBe("#timeline");
});

test("two-hour history keeps gaps and a pinned period across reload", async ({ page }) => {
  const points = [0, 2, 4, 6].map(hour => ({
    timestamp: `2026-10-14T${String(hour).padStart(2, "0")}:00:00`,
    sec_kwh_m3: hour === 4 ? null : 3 + hour / 10,
    efficiency: hour === 4 ? null : 0.7,
    flow_m3h: hour === 4 ? null : 100,
    power_kw: hour === 4 ? null : 300 + hour * 10,
    p_in_mpa: hour === 4 ? null : 1,
    p_out_mpa: hour === 4 ? null : 8,
    volume_m3: null, energy_kwh: null,
    quality: hour === 4 ? "missing" : "ready",
    basis: hour === 4 ? "none" : "interval",
    snapshot_timestamp: null,
  }));
  await page.route("**/objects/kns54an/timeline*", route => route.fulfill({ json: {
    object_id: "kns54an", aggregate_id: "НА-1", start: "2026-10-14", end: "2026-10-14",
    interval_hours: 2, basis: "interval", latest_at: "2026-10-14T06:00:00", points,
    aggregates: [{ code: "НА-1", role: "рабочий" }], observations: [], notes: [],
  } }));
  await page.goto("/?object=kns54an&aggregate=НА-1#timeline");
  await expect(page.locator("main")).toContainText("Измерения с интервалом 2 часа");
  const chart = page.getByRole("group", { name: "Удельный расход энергии", exact: true });
  await expect(chart.locator(".visx-line")).toBeAttached();
  const path = await chart.locator(".visx-line").getAttribute("d");
  expect((path?.match(/M/g) ?? []).length).toBeGreaterThan(1);
  await expect(page.getByRole("button", { name: "Разобрать режим", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "7 дней", exact: true }).click();
  await expect(page.getByLabel("Начало периода")).toHaveValue("2026-10-08");
  await page.reload();
  await expect(page.getByLabel("Начало периода")).toHaveValue("2026-10-08");
  await expect(page.getByLabel("Конец периода")).toHaveValue("2026-10-14");
});

test("an empty historical period cannot open a regime from outside that period", async ({ page }) => {
  await page.goto("/?object=kns54an&aggregate=НА-1&start=2026-01-01&end=2026-01-07#timeline");
  await expect(page.getByText("За выбранный период измерений нет.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Разобрать режим", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Начало периода")).toHaveValue("2026-01-01");
  await page.getByRole("button", { name: "Последние данные", exact: true }).click();
  await expect(page.locator(".timeline-charts svg.visx-chart").first()).toBeVisible();
});
