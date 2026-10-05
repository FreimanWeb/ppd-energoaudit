import { test, expect, type Page } from "@playwright/test";

async function selectFixture(page: Page) {
  await page.goto("/");
  await page.getByLabel("Объект", { exact: true }).selectOption("kns54an");
  await page.getByLabel("Агрегат", { exact: true }).selectOption("НА-1");
  await page.getByLabel("Дата", { exact: true }).selectOption("2026-09-29");
  await expect(page.getByText("600", { exact: true }).first()).toBeVisible();
}
async function section(page: Page, hash: string) {
  await page.locator(`nav a[href="#${hash}"]`).click();
  await expect(page.locator("main")).toBeVisible();
}
const chart = (page: Page) => page.locator(".js-plotly-plot").first();

test("real measured regime, passport and formula substitutions", async ({
  page,
}) => {
  await selectFixture(page);
  await expect(page.getByLabel("Момент измерения")).toHaveValue(
    "2026-09-29T23:30:00",
  );
  await expect(page.getByRole("heading", {name: "Паспорт и исходный режим"})).toBeVisible();
  await section(page, "snapshot");
  await expect(page.getByRole("heading", {name: "Суточный факт"})).toBeVisible();
  await section(page, "formulas");
  await expect(page.getByText(/Подстанов|Формул/).first()).toBeVisible();
  await expect(page.locator("main")).toContainText("600");
});

test("telemetry, forecast and real external CRM sources", async ({ page }) => {
  await selectFixture(page);
  await section(page, "telemetry");
  await expect(chart(page)).toBeVisible();
  await page.getByLabel("Режим телеметрии").selectOption("period");
  await page.getByLabel("Начало периода").fill("2026-07-01");
  await page.getByLabel("Конец периода").fill("2026-09-29");
  await expect(chart(page)).toBeVisible();
  await section(page, "forecast");
  await expect(chart(page)).toBeVisible();
  await section(page, "crm");
  await expect(page.getByLabel("Сценарий CRM")).toBeEnabled();
  await page.getByLabel("Сценарий CRM").selectOption("event");
  await expect(chart(page)).toBeVisible();
  await section(page, "crm-wells");
  await expect(page.getByLabel("Скважина", {exact: true}).getByRole("option", {name: "2017", exact: true})).toHaveCount(1);
  await page.getByLabel("Скважина", {exact: true}).selectOption("2017");
  await expect(page.locator("main")).toContainText("Ремонт");
  await expect(chart(page)).toBeVisible();
});

test("loss graphs, working point, measures and connection templates", async ({
  page,
}) => {
  await selectFixture(page);
  for (const hash of ["losses", "working-point"]) {
    await section(page, hash);
    await expect(chart(page)).toBeVisible();
  }
  await section(page, "measures");
  await expect(page.locator("main")).toContainText("Оптимизация уставок");
  await page.getByLabel("Основание расчёта").selectOption("forecast");
  await expect(page.getByLabel("Горизонт экономики")).toBeEnabled();
  await expect(chart(page)).toBeVisible();
  await expect(page.locator("main")).toContainText("NPV");
  await section(page, "onboarding");
  await expect(page.locator("main")).toContainText(/Шаблон|шаблон/);
});

test("unfit measurements never produce economic conclusions; missing snapshot is explicit", async ({
  page,
}) => {
  await selectFixture(page);
  await page.getByLabel("Дата", { exact: true }).selectOption("2026-09-30");
  await expect(page.getByText(/Данные непригодны/).first()).toBeVisible();
  await section(page, "measures");
  await expect(page.locator("main")).toContainText(
    /непригодн|недоступ|не рассчит/,
  );
  await expect(page.getByLabel("Горизонт экономики")).toHaveCount(0);
  await page.getByLabel("Дата", { exact: true }).selectOption("2026-10-01");
  await expect(page.getByText(/нет пригодных снимков/).first()).toBeVisible();
});

test("all source modes preserve their restrictions", async ({ page }) => {
  await selectFixture(page);
  await page.getByLabel("Режим", { exact: true }).selectOption("field_trip");
  await section(page, "overview");
  await expect(page.locator("main")).toContainText(
    /Выезд|выезд|паспорт|Паспорт/,
  );
  await page
    .getByLabel("Режим", { exact: true })
    .selectOption("telemetry_view");
  await expect(page.locator('nav a[href="#working-point"]')).toHaveAttribute("aria-disabled", "true");
  await page.evaluate(() => { location.hash = "working-point"; });
  await expect(page.locator("main")).toContainText(/анализ|недоступ|режим/);
});

test("mobile sidebar restores focus on Escape", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const toggle = page.getByRole("button", { name: "Открыть боковую панель" });
  await toggle.click();
  await expect(
    page.getByRole("button", { name: "Закрыть боковую панель" }),
  ).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Escape");
  await expect(toggle).toBeFocused();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
});

test("switching aggregate while snapshot loads discards the stale response", async ({
  page,
}) => {
  await selectFixture(page);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let started!: () => void;
  const pending = new Promise<void>((resolve) => { started = resolve; });
  await page.route("**/aggregates/**/snapshot-audit", async (route) => {
    const response = await route.fetch();
    if (decodeURIComponent(route.request().url()).includes("/НА-2/")) {
      started();
      await gate;
    }
    await route.fulfill({ response });
  });
  await page.getByLabel("Агрегат", { exact: true }).selectOption("НА-2");
  await pending;
  await page.getByLabel("Агрегат", { exact: true }).selectOption("НА-1");
  await page.getByLabel("Дата", { exact: true }).selectOption("2026-09-29");
  await expect(page.getByText("600", { exact: true }).first()).toBeVisible();
  release();
  await expect(page.getByLabel("Агрегат", { exact: true })).toHaveValue("НА-1");
  await expect(page.getByText("600", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("failed backend requests are visible and do not leave old calculations", async ({
  page,
}) => {
  await selectFixture(page);
  await page.route("**/aggregates/**/snapshots?*", (route) =>
    route.abort("failed"),
  );
  await page.getByLabel("Дата", { exact: true }).selectOption("2026-09-28");
  await expect(page.getByRole("alert").first()).toBeVisible();
  await expect(page.getByText("600", { exact: true })).toHaveCount(0);
});

test("scheme exposes real equipment and selecting a pump changes the shared aggregate", async ({
  page,
}) => {
  await selectFixture(page);
  await section(page, "scheme");
  await expect(page.locator("main svg").first()).toBeVisible();
  const pump = page.getByRole("button", { name: /НА-2/ }).first();
  await pump.click();
  await expect(page.getByLabel("Агрегат", { exact: true })).toHaveValue("НА-2");
  await expect(page.getByLabel("Выбранное оборудование")).toContainText("НА-2");
});

test("CRM unit and well graph controls affect actual plotted series", async ({
  page,
}) => {
  await selectFixture(page);
  await section(page, "crm");
  await page.getByLabel("Показатель CRM").selectOption("НА-1");
  await expect(chart(page)).toBeVisible();
  await expect(page.locator("main")).toContainText(/2\s880/);
  await section(page, "crm-wells");
  await page.getByLabel("Скважина графа").selectOption("2015");
  await expect(page.locator("main")).toContainText("2017");
  await page.getByLabel("Порог силы связи").fill("0.9");
  await expect(page.locator("main")).toContainText("Показаны 0 связей");
});
