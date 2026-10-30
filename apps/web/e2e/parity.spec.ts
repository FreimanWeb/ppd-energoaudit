import { goToSection } from "./helpers";
import { test, expect, type Page } from "@playwright/test";
import { selectDate } from "./helpers";
async function fixture(page: Page) {
  await page.goto("/#machine-block");
  await page.getByLabel("Объект", { exact: true }).selectOption("kns54an");
  await page.getByLabel("Агрегат", { exact: true }).selectOption("НА-1");
  await selectDate(page, "2026-09-29");
  await expect(page.getByRole("heading",{name:"Удельный расход энергии",exact:true})).toBeVisible();
}
test("power telemetry is a held state, and formula fractions have full accessible math layout", async ({
  page,
}) => {
  await fixture(page);
  await page.route("**/api/objects/kns54an/telemetry?*", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    const power = data.series.find(
      (series: { unit: string }) => series.unit === "кВт",
    );
    expect(power).toBeTruthy();
    power.points = power.points.map(
      (point: { timestamp: string; value: number }, index: number) => ({
        ...point,
        value: index % 2 ? 620 : 600,
      }),
    );
    await route.fulfill({ response, json: data });
  });
  await goToSection(page, "telemetry");
  const power = page.getByRole("group", { name: "P_эл", exact: true });
  await expect(power.locator("svg.visx-chart").first()).toBeVisible();
  await expect(power.locator(".visx-line")).toHaveAttribute(
    "d",
    /^M/,
  );
  const runs = await power
    .locator(".visx-line")
    .evaluate((element) => {
      const path = element as SVGPathElement;
      const length = path.getTotalLength();
      let horizontal = false,
        vertical = false;
      // Sample the SVG's actual geometry, including paths that use H/V commands.
      for (
        let distance = 0.2;
        distance < length - 0.2;
        distance += Math.max(0.5, length / 1000)
      ) {
        const a = path.getPointAtLength(distance - 0.1),
          b = path.getPointAtLength(distance + 0.1);
        const dx = Math.abs(b.x - a.x),
          dy = Math.abs(b.y - a.y);
        if (dx < 0.001 && dy > 0.01) vertical = true;
        if (dy < 0.001 && dx > 0.01) horizontal = true;
      }
      return { horizontal, vertical };
    });
  expect(runs.horizontal).toBeTruthy();
  expect(runs.vertical).toBeTruthy();
  await goToSection(page, "formulas");
  await page.getByRole("button", { name: "Раскрыть все", exact: true }).click();
  await expect(
    page.locator(".formula-card .katex-display").first(),
  ).toBeVisible();
  await expect
    .poll(() => page.locator(".formula-card math mfrac").count())
    .toBeGreaterThan(0);
  await expect
    .poll(() => page.locator(".formula-card math msub").count())
    .toBeGreaterThan(0);
});
test("scenario measures retain energy benefit but never claim known capital or payback", async ({
  page,
}) => {
  await fixture(page);
  await goToSection(page, "measures");
  await page.locator('[data-action-id="annual:efficiency_recovery_scenario"]').getByRole('link',{name:/Подробнее/}).click();
  const detail=page.getByRole('region',{name:'Мероприятие',exact:true});
  await expect(detail.locator('.network-balance-totals dd').filter({hasText:'Требует оценки'})).toHaveCount(2);
  await detail.getByRole('button',{name:'Инвестиционная оценка',exact:true}).click();
  await expect(
    page.locator(".page-kpis strong").filter({ hasText: "Требует оценки" }),
  ).toHaveCount(4);
  await expect(page.locator("main")).toContainText(
    "CAPEX требует оценки; NPV и окупаемость не определены.",
  );
  await page
    .getByRole("button", { name: "Пояснение: Денежный поток", exact: true })
    .focus();
  await expect(page.getByRole("tooltip")).toContainText(
    "линия окупаемости не построена",
  );
});
