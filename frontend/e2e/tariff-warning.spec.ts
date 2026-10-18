import { goToSection } from "./helpers";
import { test, expect } from "@playwright/test";

test("fallback tariff warning stays visible across audit sections", async ({page}) => {
  const warning = "Для даты 2027-01-01 тариф не задан. Применён ближайший тариф 5,17 ₽/кВт·ч за период 2026-01-01 — 2026-12-31.";
  await page.route("**/snapshot-audit", async route => {
    const response = await route.fetch();
    const audit = await response.json();
    await route.fulfill({response,json:{...audit,tariff_warning:warning}});
  });
  await page.goto("/?object=kns54an&aggregate=НА-1&day=2026-09-29#machine-block");
  await expect(page.getByRole("status").filter({hasText:warning})).toBeVisible();
  await goToSection(page, "losses");
  await expect(page.getByRole("status").filter({hasText:warning})).toBeVisible();
  await goToSection(page, "measures");
  await page.getByText("Расширенный расчёт экономики машинного блока",{exact:true}).click();
  await expect(page.getByRole("status").filter({hasText:warning})).toBeVisible();
  await expect(page.getByText("Годовой реестр мероприятий",{exact:true})).toBeVisible();
});
