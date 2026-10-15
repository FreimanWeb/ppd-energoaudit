import { test, expect } from "@playwright/test";

test("portfolio calendar stays within the viewport and selects the history end", async ({page}) => {
  await page.goto("/#portfolio");
  const trigger = page.getByRole("button", {name:"Дата окончания графиков",exact:true});
  for (const [width,height] of [[1280,800],[320,568],[266,400]]) {
    await page.setViewportSize({width,height});
    await trigger.click();
    const dialog = page.getByRole("dialog", {name:"Выбор даты",exact:true});
    await expect(dialog).toBeVisible();
    await expect.poll(async () => dialog.evaluate(el => {
      const box=el.getBoundingClientRect();
      return box.left>=0 && box.right<=innerWidth && box.top>=0 && box.bottom<=innerHeight;
    })).toBe(true);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
  }
  await trigger.click();
  await page.getByLabel("Месяц календаря").fill("2026-09");
  await page.getByRole("button",{name:"2026-09-29",exact:true}).click();
  await expect(trigger).toHaveAttribute("data-date","2026-09-29");
  await expect(page.locator(".portfolio-history-range time").last()).toHaveAttribute("datetime","2026-09-29");
});
