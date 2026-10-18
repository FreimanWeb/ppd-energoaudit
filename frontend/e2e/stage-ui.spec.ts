import { test, expect } from "@playwright/test";

const context = "/?object=demo-ppd&aggregate=НА-1&day=2026-10-18";

test("machine diagnostics are visible immediately without duplicate navigation", async ({page}) => {
  await page.setViewportSize({width:1440,height:900});
  await page.goto(context + "#machine-block");
  await expect(page.getByText("КПД насоса расчётный", {exact:true})).toBeVisible();
  await expect(page.getByRole("button", {name:"Диагностика агрегата",exact:true})).toHaveCount(0);
  await expect(page.getByRole("navigation", {name:"Навигация по потерям"})).toHaveCount(0);
  await expect(page.locator(".stage-losses")).not.toContainText("2026-10-18T");
  const efficiency = page.locator(".machine-efficiency");
  const main = (await efficiency.locator(":scope > .metric-values").boundingBox())!;
  const diagnostics = (await efficiency.locator(":scope > .metric-group").boundingBox())!;
  expect(diagnostics.x).toBeGreaterThan(main.x + main.width);
  expect(Math.abs(diagnostics.y - main.y)).toBeLessThan(20);
  const action = page.getByRole("link", {name:"Перейти к мероприятиям",exact:true});
  await expect(action).toHaveClass(/ds-button/);
  await action.click();
  await expect.poll(() => new URL(page.url()).hash).toBe("#measures");
  expect(new URL(page.url()).searchParams.get("aggregate")).toBe("НА-1");
});

test("stage assumptions stay readable and scroll within the table on small screens", async ({page}) => {
  await page.setViewportSize({width:1024,height:900});
  await page.goto(context + "#wells");
  await page.getByText("Исходные данные и допущения",{exact:true}).click();
  const table = page.locator(".stage-assumptions table");
  await expect(table).toBeVisible();
  const widths = await table.locator("th").evaluateAll(nodes=>nodes.map(n=>n.getBoundingClientRect().width));
  expect(widths[4]).toBeGreaterThanOrEqual(230);
  const row = await table.locator("tbody tr").first().boundingBox();
  expect(row!.height).toBeLessThan(110);
  await page.setViewportSize({width:320,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  const scroll = page.locator(".stage-assumptions .table-scroll");
  expect(await scroll.evaluate(el=>el.scrollWidth>el.clientWidth)).toBe(true);
});
