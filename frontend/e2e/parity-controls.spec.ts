import { test, expect, type Page, type Locator } from "@playwright/test";
import { selectDate } from "./helpers";

async function fixture(page: Page) {
  await page.goto("/");
  await page.getByLabel("Объект", { exact: true }).selectOption("kns54an");
  await page.getByLabel("Агрегат", { exact: true }).selectOption("НА-1");
  await selectDate(page, "2026-09-29");
  await expect(page.getByText("600", { exact: true }).first()).toBeVisible();
}
async function section(page: Page, hash: string) {
  await page.locator(`nav a[href="#${hash === "scheme" ? "overview" : hash}"]`).click();
}

test("water and NGDU filters actually constrain selectable objects and reset safely", async ({
  page,
}) => {
  await fixture(page);
  const all = await page
    .getByLabel("Объект", { exact: true })
    .locator("option")
    .count();
  await page
    .locator(".object-filter")
    .filter({ hasText: "Тип воды" })
    .locator("summary")
    .click();
  await page.getByLabel("Тип воды: пресная", { exact: true }).check();
  await expect(
    page
      .getByLabel("Объект", { exact: true })
      .locator('option[value="kns54an"]'),
  ).toHaveCount(0);
  expect(
    await page.getByLabel("Объект", { exact: true }).locator("option").count(),
  ).toBeLessThan(all);
  await page.getByLabel("Тип воды: пресная", { exact: true }).uncheck();
  await page
    .locator(".object-filter")
    .filter({ hasText: "НГДУ" })
    .locator("summary")
    .click();
  await page.getByLabel("НГДУ: Азнакаевскнефть", { exact: true }).check();
  await expect(
    page
      .getByLabel("Объект", { exact: true })
      .locator('option[value="kns97pren"]'),
  ).toHaveCount(0);
  await expect(
    page
      .getByLabel("Объект", { exact: true })
      .locator('option[value="kns54an"]'),
  ).toHaveCount(1);
  await page.getByLabel("НГДУ: Азнакаевскнефть", { exact: true }).uncheck();
  await expect(
    page.getByLabel("Объект", { exact: true }).locator("option"),
  ).toHaveCount(all);
});

test("calendar statuses distinguish valid and unfit days and changing month can select history", async ({
  page,
}) => {
  await fixture(page);
  await page.getByRole("button", { name: "Дата", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "2026-09-29: Пригодные сутки",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "2026-09-30: Непригодные данные",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("button", { name: "Дата", exact: true }),
  ).toHaveAttribute("data-date", "2026-09-30");
  await expect(
    page.getByText("Данные непригодны для достоверных выводов"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Дата", exact: true }).click();
  await page.getByLabel("Месяц календаря").fill("2026-07");
  await page
    .getByRole("button", { name: "2026-07-01: Пригодные сутки", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Дата", exact: true }),
  ).toHaveAttribute("data-date", "2026-07-01");
  await expect(page.getByLabel("Момент измерения")).toHaveValue(
    "2026-07-01T23:30:00",
  );
  await page.getByRole("button", { name: "Дата", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "2026-07-01: Пригодные сутки",
      exact: true,
    }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Escape");
});

test("forecast periodicity uses legacy defaults and preserves history before zero", async ({
  page,
}) => {
  await fixture(page);
  await section(page, "forecast");
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("group", { name: "Факт и прогноз закачки", exact: true })).toBeVisible();
  await expect(page.getByLabel("Горизонт прогноза")).toHaveValue("36");
  await expect(page.getByLabel("Конец периода")).toHaveValue("2026-10-01");
  await page.getByLabel("Периодичность").selectOption("7");
  await expect(page.getByLabel("Горизонт прогноза")).toHaveValue("52");
  await page.getByLabel("Периодичность").selectOption("1");
  await expect(page.getByLabel("Горизонт прогноза")).toHaveValue("1095");
  const horizonResponse = page.waitForResponse(response => new URL(response.url()).searchParams.get("horizon") === "1500" && response.status() === 200);
  await page.getByLabel("Горизонт прогноза").fill("1500");
  await horizonResponse;
  const plot = page.getByRole("group", {
    name: "Факт и прогноз закачки",
    exact: true,
  });
  await expect(plot.locator("svg.visx-chart")).toBeVisible();
  await expect(
    plot.getByRole("button", { name: "Прогноз", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect.poll(async () => {
    await hoverLineEnd(page, plot, "Прогноз");
    return plot.locator(".native-chart-tooltip strong").textContent();
  }).toBe("1500");
  const firstX = async (name: string) =>
    plot
      .locator(`.visx-line[name="${name}"]`)
      .evaluate((el) => (el as SVGPathElement).getPointAtLength(0).x);
  expect(await firstX("Факт")).toBeLessThan(await firstX("Прогноз"));
  await hoverLineEnd(page, plot, "Факт", true);
  await expect
    .poll(async () =>
      Number(
        (
          await plot.locator(".native-chart-tooltip strong").textContent()
        )?.replace(/\s/g, ""),
      ),
    )
    .toBeLessThan(0);
  await page.getByLabel("Периодичность").selectOption("30");
  await expect(page.getByLabel("Горизонт прогноза")).toHaveValue("36");
});

test("no telemetry object stays honest in analysis and field trip uses measured passport values", async ({
  page,
}) => {
  await fixture(page);
  await page.getByLabel("Объект", { exact: true }).selectOption("kns97pren");
  await expect(page.getByLabel("Дата", { exact: true })).toBeDisabled();
  await expect(page.locator("main")).toContainText(/нет.*телеметр|нет дат/i);
  await expect(page.getByText("600", { exact: true })).toHaveCount(0);
  await page.getByLabel("Агрегат", { exact: true }).selectOption("НА-2 ПР");
  await page.getByLabel("Режим", { exact: true }).selectOption("field_trip");
  await expect(
    page.getByRole("heading", { name: "Паспорт и исходный режим" }),
  ).toBeVisible();
  await expect(page.locator("main")).toContainText("Выезд");
  await expect(page.locator("main")).toContainText("189");
  await expect(page.locator("main")).toContainText("40,25");
  await expect(page.locator("main")).toContainText("9,6");
  await expect(page.getByLabel("Дата", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await section(page, "working-point");
  await expect(page.locator("svg.visx-chart").first()).toBeVisible();
});

test("onboarding exposes readiness and both read-only templates for the actual selected aggregate", async ({
  page,
}) => {
  await fixture(page);
  await section(page, "onboarding");
  await expect(
    page.getByRole("heading", { name: "Готовность выбранного агрегата" }),
  ).toBeVisible();
  await expect(page.locator("main table").first()).toContainText("Есть");
  await page.getByText("Шаблон паспорта объекта", { exact: true }).click();
  await expect(page.locator("pre").first()).toContainText("aggregates");
  await page
    .getByText("Шаблон записи для верификации", { exact: true })
    .click();
  await expect(page.locator("pre").last()).toContainText(
    "config/verification.yaml",
  );
  await expect(page.locator("main input, main textarea")).toHaveCount(0);
});

test("a chosen measurement remains shared across sources, formulas and the overview scheme", async ({
  page,
}) => {
  await fixture(page);
  const auditResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/snapshot-audit") &&
      r.request().postDataJSON()?.timestamp === "2026-09-29T12:00:00",
  );
  await page.getByLabel("Момент измерения").selectOption("2026-09-29T12:00:00");
  expect((await auditResponse).status()).toBe(200);
  await section(page, "sources");
  await expect(page.locator("main")).toContainText("e2e-scada.csv");
  await expect(page.getByLabel("Момент измерения")).toHaveValue("2026-09-29T12:00:00");
  await section(page, "formulas");
  await expect(page.locator(".formula-card").first()).toBeVisible();
  await expect(page.getByLabel("Момент измерения")).toHaveValue(
    "2026-09-29T12:00:00",
  );
  await section(page, "scheme");
  await expect(page.locator(".pump-regime-card")).toContainText("600");
  await expect(page.locator(".scheme-tools")).toHaveCount(0);
  await expect(page.locator(".equipment-scheme > g[transform]")).toHaveCount(0);
  await expect(page.getByLabel("Момент измерения")).toHaveValue(
    "2026-09-29T12:00:00",
  );
});

test("CRM scenario and aggregate choice change the true predicted series and graph click selects a well", async ({
  page,
}) => {
  await fixture(page);
  await section(page, "crm");
  await page.getByLabel("Сценарий CRM").selectOption("baseline");
  const plot = page.getByRole("group", {
    name: "CRM и фактическая подача",
    exact: true,
  });
  const predicted = async () => {
    await hoverLineEnd(page, plot, "Прогноз CRM");
    const tooltip = plot
      .locator(".native-chart-tooltip p")
      .filter({ hasText: "Прогноз CRM" });
    return Number(
      (await tooltip.locator("b").textContent())?.replace(/\s/g, "").replace("м³/сут", ""),
    );
  };
  await expect.poll(predicted).toBe(5760);
  await page.getByLabel("Показатель CRM").selectOption("НА-1");
  await expect.poll(predicted).toBe(2880);
  await page.getByLabel("Сценарий CRM").selectOption("event");
  await expect.poll(predicted).toBe(4800);
  await page.getByLabel("Показатель CRM").selectOption("НА-1");
  await expect.poll(predicted).toBe(2400);
  await section(page, "crm-wells");
  await page.getByRole("button", { name: "Связи", exact: true }).click();
  const node = page.getByRole("button", { name: "Скважина 2015", exact: true });
  await expect(node).toBeVisible();
  await node.click();
  await expect(page.getByLabel("Скважина графа")).not.toHaveValue("");
  await expect(page.locator("main")).toContainText("Связанная скважина");
});

test("CRM graph preserves downtime square markers from the legacy wells view", async ({
  page,
}) => {
  await fixture(page);
  await section(page, "crm-wells");
  await page.getByRole("button", { name: "Связи", exact: true }).click();
  const downtime = page.getByRole("button", {
    name: "Скважина 2017",
    exact: true,
  });
  await expect(downtime.locator("rect.network-marker")).toBeVisible();
  await expect(downtime.locator("circle.network-marker")).toHaveCount(0);
});

test("selected pump exposes the legacy engineering assessment alongside pressures", async ({
  page,
}) => {
  await fixture(page);
  await section(page, "scheme");
  await page.getByRole("button", { name: /НА-1/ }).first().click();
  const equipment = page.getByLabel("Выбранное оборудование");
  await expect(equipment).toContainText(/КПД.*факт|Фактический КПД/i);
  await expect(equipment).toContainText(/КПД.*ном|Номинальный КПД/i);
  await expect(equipment).toContainText(/загрузк|K_з|Kз/i);
  await expect(equipment).toContainText(/УРЭ|Удельный расход/i);
  await expect(equipment).toContainText(/потери.*КПД|Потери по КПД/i);
});

test("scheme stage details retain the physical meaning of source and throttling", async ({
  page,
}) => {
  await fixture(page);
  await section(page, "scheme");
  await page.getByRole("button", { name: "Приём воды", exact: true }).click();
  await expect(page.getByLabel("Выбранное оборудование")).toContainText(
    "Подача за сутки",
  );
  await page
    .getByRole("button", { name: "ЗРА / штуцеры", exact: true })
    .click();
  await expect(page.getByLabel("Выбранное оборудование")).toContainText(
    "дросселирование",
  );
});

async function hoverLineEnd(
  page: Page,
  plot: Locator,
  name: string,
  atStart = false,
) {
  const line = plot.locator(`.visx-line[name="${name}"]`);
  await expect(plot.locator("svg.visx-chart").first()).toBeVisible();
  await expect(line).toBeAttached();
  await expect
    .poll(() => line.evaluate((el) => (el as SVGPathElement).getTotalLength()))
    .toBeGreaterThan(0);
  await plot.scrollIntoViewIfNeeded();
  const point = await line.evaluate((el, atStart) => {
    const path = el as SVGPathElement;
    const p = path.getPointAtLength(atStart ? 0 : path.getTotalLength());
    const matrix = path.getScreenCTM();
    if (!matrix) throw new Error("SVG has no screen transform");
    return {
      x: p.x * matrix.a + p.y * matrix.c + matrix.e,
      y: p.x * matrix.b + p.y * matrix.d + matrix.f,
    };
  }, atStart);
  await page.mouse.move(point.x, point.y);
}
