import { test, expect } from "@playwright/test";

const context = "/?object=demo-ppd&aggregate=НА-1&day=2026-10-18";

test("machine loss selection opens measures for the same aggregate", async ({page}) => {
  await page.setViewportSize({width:1440,height:900});
  await page.goto(context + "#machine-block");
  await expect(page.getByText("КПД насоса расчётный", {exact:true})).toBeVisible();
  await page.getByRole("navigation",{name:"Вкладки: Машинный блок",exact:true}).getByRole("link",{name:"Карта потерь",exact:true}).click();
  await page.getByRole("button",{name:/^Потери в насосе/}).click();
  await page.getByLabel("Действия для составляющей").getByRole("link",{name:"Мероприятия",exact:true}).click();
  await expect.poll(() => new URL(page.url()).hash).toBe("#measures");
  expect(new URL(page.url()).searchParams.get("aggregate")).toBe("НА-1");
});

