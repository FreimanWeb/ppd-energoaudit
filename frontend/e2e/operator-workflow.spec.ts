import { goToSection } from "./helpers";
import { test, expect } from "@playwright/test";

test("aggregate options reflect the catalogue and chain scenario belongs to overview", async ({page}) => {
  await page.goto("/?object=demo-ppd&aggregate=НА-1#measures");
  const aggregate = page.getByLabel("Агрегат",{exact:true});
  await expect(aggregate.locator('option[value="НА-1"]')).toHaveCount(1);
  await expect(aggregate.locator("option")).toHaveCount(2);
  await expect(aggregate.locator('option[value=""]')).toHaveCount(0);
  await page.locator(".sidebar-nav").getByRole("link",{name:"Обзор",exact:true}).click();
  const tabs = page.getByRole("navigation",{name:"Вкладки: Обзор",exact:true});
  await tabs.getByRole("link",{name:"Карта потерь",exact:true}).click();
  await expect(page.locator('.sidebar-nav a[aria-current="page"]')).toHaveText("Обзор");
  expect(new URL(page.url()).hash).toBe("#losses");
  await page.locator(".sidebar-nav").getByRole("link",{name:"Трубопроводы",exact:true}).click();
  await expect(page.locator(".page-tabs a").filter({hasText:"Карта потерь"})).toHaveCount(0);
});

test("operator sees three working objects and explores demo by process area", async ({page}) => {
  await page.goto("/#portfolio");
  await expect(page.locator(".portfolio-card")).toHaveCount(4);
  await expect(page.locator(".portfolio-object-meta")).toHaveText([
    /demo-ppd|kns54an|knsopu|kns97pren/, /demo-ppd|kns54an|knsopu|kns97pren/,
    /demo-ppd|kns54an|knsopu|kns97pren/, /demo-ppd|kns54an|knsopu|kns97pren/,
  ]);
  await page.getByRole("button",{name:"Открыть историю: Демо · КНС",exact:true}).click();
  await expect.poll(() => new URL(page.url()).hash).toBe("#timeline");
  await page.getByRole("navigation",{name:"Вкладки: Обзор",exact:true}).getByRole("link",{name:"Схема и участки",exact:true}).click();
  await expect(page.getByRole("heading",{name:"КПД",exact:true})).toHaveCount(0);
  const diagram = page.locator(".equipment-scheme");
  await expect(diagram.getByRole("button")).toHaveCount(0);
  await expect(page.locator(".scheme-loss-value")).toHaveText([/%/,/%/,/%/]);
  await diagram.getByRole("link",{name:"Открыть участок: Машинный блок",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Машинный блок",exact:true})).toBeVisible();
  await expect(page.getByRole("heading",{name:"КПД",exact:true})).toBeVisible();
  await expect(page.getByRole("navigation",{name:"Вкладки: Машинный блок",exact:true}).getByRole("link",{name:"Рабочая точка",exact:true})).toBeVisible();
  await expect(page.getByRole("group",{name:"КПД агрегата",exact:true})).toBeVisible();
  const context = new URL(page.url()).search;
  await goToSection(page, "overview");
  await diagram.getByRole("link",{name:"Открыть участок: Трубопроводы",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Трубопроводы",exact:true}).first()).toBeVisible();
  expect(new URL(page.url()).search).toBe(context);
  await expect(page.getByRole("region",{name:"Потери по участкам трубопроводов",exact:true})).toContainText("main");
  await goToSection(page, "overview");
  await diagram.getByRole("link",{name:"Открыть участок: Скважины и арматура",exact:true}).click();
  await expect(page.getByRole("region",{name:"Потери по скважинам",exact:true})).toBeVisible();
  await page.setViewportSize({width:320,height:844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});

test("shared URLs for hidden objects switch to an available working object", async ({page}) => {
  await page.goto("/?object=kns10bn#timeline");
  await expect.poll(() => new URL(page.url()).searchParams.get("object")).toBe("kns54an");
  await expect(page.getByLabel("Объект",{exact:true}).locator('option:not([value=""])')).toHaveCount(4);
});
