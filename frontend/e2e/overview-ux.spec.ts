import { test, expect } from "@playwright/test";

test("overview has compact KPI cards, explicit comparisons and keyboard help", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route("**/snapshot-audit", async route => {
    const response = await route.fetch();
    const audit = await response.json();
    Object.assign(audit.audit.metrics, {sec_fact_kwh_m3: 4, sec_calc_kwh_m3: 3, eta_unit: .6, eta_nom: .8,
      eta_motor_real: .6, eta_pump: .5, load_factor: 1.1, h_fact_m: 100, h_due_m: 110});
    audit.passport.motor.eta_nom = .9;
    audit.passport.pump.eta_nom = .8;
    await route.fulfill({response, json: audit});
  });
  await page.goto("/?object=kns54an&aggregate=" + encodeURIComponent("НА-1") + "&day=2026-09-29#overview");
  const ure = page.locator('.ure-panel .metric-segment').filter({ has: page.getByText("Факт", { exact: true }) });
  await expect(ure).toHaveAttribute("data-tone", "bad");
  await expect(ure.locator(".metric-caption")).toHaveCount(0);
  await ure.locator("strong").hover();
  await expect(page.getByRole("tooltip")).toContainText("Превышение требует внимания");
  await page.keyboard.press("Escape");
  const box = await ure.boundingBox();
  expect(box!.width).toBeLessThanOrEqual(200);
  await ure.getByRole("button", {name: "Пояснение: Факт"}).focus();
  await expect(page.getByRole("tooltip")).toContainText("W / Q_сут");
  await expect(page.locator('.metric-segment').filter({has: page.getByText("КПД агрегата", {exact: true})})).toHaveAttribute("data-tone", "bad");
  const badEfficiency = page.locator('.metric-segment').filter({ has: page.getByText('КПД агрегата', { exact: true }) }).locator('strong');
  expect(await ure.locator('strong').evaluate(element => getComputedStyle(element).color)).toBe(await badEfficiency.evaluate(element => getComputedStyle(element).color));
  await expect(page.getByRole("button", {name: "Пояснение: Подача"})).toBeVisible();
  await page.getByText("Диагностика агрегата", { exact: true }).click();
  for (const label of ["КПД ЭД расчётный", "КПД насоса расчётный", "Коэффициент загрузки ЭД", "Фактический напор"])
    await expect(page.locator(".metric-card").filter({has: page.getByText(label, {exact: true})})).toHaveAttribute("data-tone", "bad");
  await expect(page.getByRole("button", {name: "Сравнение", exact: true})).toHaveCount(0);
  await expect(ure).toBeVisible();
  await expect(page.getByRole("group", {name: "Структура подведённой мощности", exact: true})).toHaveCount(0);
  await expect(page.getByRole("link", {name: "Карта потерь мощности →", exact: true})).toHaveCount(0);
  await expect(page.getByRole("columnheader", {name: /Затраты CAPEX/})).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("unfit overview never marks a measured KPI as good", async ({page}) => {
  await page.route("**/snapshot-audit", async route => {
    const response = await route.fetch();
    const audit = await response.json();
    audit.quality.status = "unfit";
    Object.assign(audit.audit.metrics, {sec_fact_kwh_m3: 2, sec_calc_kwh_m3: 3, eta_unit: 1.2});
    await route.fulfill({response, json: audit});
  });
  await page.goto("/?object=kns54an&aggregate=" + encodeURIComponent("НА-1") + "&day=2026-09-29#overview");
  await expect(page.locator("main")).toContainText("Данные непригодны");
  await expect(page.locator('.metric-card[data-tone="good"]')).toHaveCount(0);
  const eta = page.locator(".metric-segment").filter({has: page.getByText("КПД агрегата", {exact: true})});
  await eta.locator("strong").hover();
  await expect(page.getByRole("tooltip")).toContainText("Физическая ошибка");
});
