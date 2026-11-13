import { test, expect } from "@playwright/test";

for (const pumpEfficiency of [0.78, null]) {
  test(`working point compares pump efficiency, including missing value ${pumpEfficiency}`, async ({ page }) => {
    await page.route("**/working-point", async route => {
      await route.fulfill({ json: {
        qh: [{ q: 80, h: 1200 }, { q: 120, h: 800 }],
        qeta: [{ q: 80, eta: 0.7 }, { q: 120, eta: 0.8 }], system: [],
        point: { q: 100, h: 1000, eta: 0.65, eta_pump: pumpEfficiency },
        nominal: { q: 100, h: 1000, eta: 0.8 }, due: { h: null, eta: null },
        origin: { qh: "passport", qeta: "passport", system: "unavailable" },
        notes: [], pump_kind: "центробежный",
        ranges: { qh: [80, 120], qeta: [80, 120] },
      } });
    });
    await page.goto("/?object=kns54an&aggregate=" + encodeURIComponent("НА-1") + "&day=2026-09-29#working-point");
    const chart = page.getByRole("group", { name: "Характеристика Q–η", exact: true });
    await expect(chart.getByRole("button", { name: "КПД насоса (расчётный)", exact: true })).toBeVisible();
    await expect(chart.getByRole("button", { name: "КПД установки (факт)", exact: true })).toHaveCount(0);
    const marker = chart.locator('.visx-point circle');
    if (pumpEfficiency != null) {
      await marker.hover();
      await expect(chart.locator(".native-chart-tooltip")).toContainText("78");
      await expect(chart.locator(".native-chart-tooltip")).not.toContainText("65");
    } else {
      await expect(marker).toHaveCount(0);
      await expect(page.getByText("Расчётный КПД насоса недоступен", { exact: false })).toBeVisible();
    }
    await expect(page.locator("main")).toContainText("КПД установки 65");
  });
}
