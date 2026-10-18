import { test, expect } from "@playwright/test";

test("navigation precedes analysis settings and measures belong to the whole chain", async ({page}) => {
  await page.goto("/?object=demo-ppd#machine-block");
  const navigation = page.getByRole("navigation",{name:"Разделы энергоаудита",exact:true});
  const settings = page.locator(".analysis-panel");
  await expect(settings).toBeVisible();
  expect((await navigation.boundingBox())!.y).toBeLessThan((await settings.boundingBox())!.y);
  await expect(page.getByRole("navigation",{name:"Вкладки: Машинный блок",exact:true}).getByRole("link",{name:"Мероприятия",exact:true})).toHaveCount(0);
  await navigation.getByRole("link",{name:"Мероприятия",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Мероприятия по участкам",exact:true})).toBeVisible();
  await page.getByLabel("Участок мероприятий",{exact:true}).selectOption("pipes");
  const pipes=page.locator('.action-list [data-stage="pipes"]').first();
  await expect(pipes).toContainText("Очистить трубы");
  await pipes.getByRole("link",{name:/Подробнее/}).click();
  await page.getByRole("region",{name:"Мероприятие",exact:true}).getByRole("button",{name:"Оценить сценарий",exact:true}).click();
  await expect(page.getByLabel("Результат сценария мероприятия",{exact:true})).toContainText("После");
});
