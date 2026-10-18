import {goToSection, selectDate} from "./helpers";
import { test, expect } from "@playwright/test";

test("chain map is separate from hydraulic scenarios and well history", async ({page}) => {
  await page.goto("/?object=demo-ppd&aggregate=НА-1&day=2026-10-01&timestamp=2026-10-01T00:30:00#losses");
  const map = page.locator(".page-panel").filter({has:page.getByRole("heading",{name:"Карта потерь по цепочке",exact:true})});
  await expect(map.getByLabel("Потери по участкам цепочки")).toBeVisible();
  await expect(page.getByRole("navigation",{name:"Вкладки: Обзор"}).getByRole("link",{name:"Карта потерь",exact:true})).toHaveAttribute("aria-current","page");
  await expect(map.locator(".network-scenario, .network-actions, .network-comparison")).toHaveCount(0);
  await expect(page.getByRole("heading",{name:"История нагнетательных скважин",exact:true})).toHaveCount(0);
  const context = new URL(page.url()).search;
  await map.getByRole("link",{name:"Гидравлический сценарий",exact:true}).click();
  await expect(page.locator('.sidebar-nav a[aria-current="page"]')).toHaveText("Трубопроводы");
  expect(new URL(page.url()).search).toBe(context);
  await expect(page.locator(".network-scenario")).toBeVisible();
  await expect(page.getByRole("heading",{name:"История нагнетательных скважин",exact:true})).toHaveCount(0);
  await goToSection(page,"well-history");
  await expect(page.getByRole("heading",{name:"История нагнетательных скважин",exact:true})).toBeVisible();
  expect(new URL(page.url()).search).toBe(context);
});

test("timeline keeps the selected regime through chain losses and measure comparison", async ({page}) => {
  await page.goto("/?object=kns54an&aggregate=НА-1&start=2026-09-27&end=2026-09-29#timeline");
  await expect(page.locator(".comparison-table")).toContainText("УРЭ");
  await selectDate(page,"2026-09-29");
  await page.getByLabel("Момент измерения",{exact:true}).selectOption("2026-09-29T23:30:00");
  await goToSection(page,"losses");
  await expect.poll(() => new URL(page.url()).hash).toBe("#losses");
  await expect.poll(() => new URL(page.url()).searchParams.get("day")).toBe("2026-09-29");
  const snapshot = new URL(page.url()).searchParams.get("timestamp");
  expect(snapshot).toBe("2026-09-29T23:30:00");
  await page.getByRole("link",{name:"Гидравлический сценарий",exact:true}).click();
  const heading = page.getByRole("heading", {name:"Гидравлический сценарий",exact:true});
  await expect(heading).toBeVisible();
  const panel = page.locator(".page-panel").filter({has:heading});
  await expect(panel.getByLabel("Потери по участкам цепочки")).toContainText("Машинный зал и обвязка");
  await expect(panel.getByLabel("Потери по участкам цепочки").locator("dd")).toHaveCount(3);
  await expect(panel.getByText("Приоритетные мероприятия", {exact:true})).toBeVisible();
  await panel.getByRole("button", {name:"Поток мощности",exact:true}).click();
  await panel.getByRole("button", {name:"Трение в трубопроводах",exact:true}).click();
  await expect(panel.getByText("Мероприятия по выбранной составляющей", {exact:true})).toBeVisible();
  await expect(panel.getByRole("button", {name:"Оценить сценарий",exact:true})).toHaveCount(1);
  await page.setViewportSize({width:390,height:844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const request = page.waitForResponse(response => response.url().endsWith("/network-losses") && Boolean(response.request().postDataJSON()?.intervention));
  await panel.getByRole("button", {name:"Оценить сценарий",exact:true}).first().click();
  const response = await request;
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.comparison.measure_id).toBe("clean_pipes");
  expect(result.context.timestamp).toBe(snapshot);
  expect(result.comparison.after.input_kw).toBeLessThan(result.comparison.before.input_kw);
  expect(Math.abs(result.comparison.after.balance_error_kw)).toBeLessThan(1e-7);
  await expect(page.getByLabel("Результат мероприятия",{exact:true})).toContainText("Прогнозируемое снижение мощности");
  await panel.getByRole("button", {name:"Вернуться к исходному сценарию",exact:true}).click();
  await expect(page.getByLabel("Результат мероприятия",{exact:true})).toHaveCount(0);
  await goToSection(page,"timeline");
  await expect.poll(() => new URL(page.url()).hash).toBe("#timeline");
  await expect(page.getByLabel("Конец периода")).toHaveValue("2026-09-29");
});

test("infeasible chain does not offer savings", async ({page}) => {
  await page.goto("/?object=kns54an&aggregate=НА-1&day=2026-09-29#network-scenario");
  const panel = page.locator(".page-panel").filter({has:page.getByRole("heading", {name:"Гидравлический сценарий",exact:true})});
  await panel.getByText("Параметры сценария",{exact:true}).click();
  await panel.getByLabel("Требуемое полезное давление без перепада высот, МПа").fill("30");
  await panel.getByRole("button",{name:"Пересчитать сценарий",exact:true}).click();
  await expect(panel.getByRole("alert")).toContainText("физически невыполним");
  await expect(panel.getByRole("button",{name:"Оценить сценарий",exact:true})).toHaveCount(0);
  await expect(panel.getByLabel("Результат мероприятия",{exact:true})).toHaveCount(0);
});

test("unfit measurements show an unavailable chain without crashing", async ({page}) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/?object=kns54an&aggregate=НА-1&day=2026-09-30#losses");
  await expect(page.getByRole("alert")).toContainText("Карта всей цепочки недоступна");
  await expect(page.getByRole("button",{name:"Оценить сценарий",exact:true})).toHaveCount(0);
  expect(errors).toEqual([]);
});
