import { test, expect } from "@playwright/test";
import { selectDate } from "./helpers";

test("history presents four KPI cards without repeated introductory text", async ({page}) => {
  await page.goto("/?object=demo-ppd#timeline");
  await expect(page.locator(".timeline-kpi .metric-card")).toHaveCount(4);
  await expect(page.locator(".timeline-kpi time").first()).toBeVisible();
  for (const card of await page.locator(".timeline-kpi").all()) {
    const missing = await card.locator("strong").textContent() === "Нет данных";
    await expect(card.locator("time")).toHaveCount(missing ? 0 : 1);
  }
  await expect(page.getByText("Последние доступные данные",{exact:true})).toHaveCount(0);
  await expect(page.getByText(/Значения не означают состояние в реальном времени/)).toHaveCount(0);
  await expect(page.getByText("Демо · КНС · Обзор состояния и история работы",{exact:true})).toHaveCount(0);
  await expect(page.locator(".timeline-view > p > a")).toHaveCount(0);
  const parameters = page.locator("details.analysis-panel");
  await expect(parameters.locator(".selector-filters")).toHaveCount(1);
  await parameters.locator(":scope > summary").click();
  await expect(page.getByLabel("Объект",{exact:true})).not.toBeVisible();
  await parameters.locator(":scope > summary").click();
  await expect(page.getByLabel("Объект",{exact:true})).toBeVisible();
  await page.setViewportSize({width:320,height:844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});

test("measurement time follows the date on a separate row", async ({page}) => {
  await page.goto("/?object=demo-ppd#machine-block");
  const day = page.getByRole("button",{name:"Дата",exact:true});
  const time = page.getByLabel("Момент измерения",{exact:true});
  await expect(day).toBeEnabled();
  await time.scrollIntoViewIfNeeded();
  const a = (await day.boundingBox())!, b = (await time.boundingBox())!;
  expect(b.y).toBeGreaterThanOrEqual(a.y+a.height);
});

test("chart selection and analysis parameters share one timestamp without navigation", async ({page}) => {
  await page.goto("/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T18:00:00#timeline");
  const time = page.getByLabel("Момент измерения",{exact:true});
  await expect(time).toHaveValue("2026-10-18T18:00:00");
  const chart = page.locator(".timeline-charts svg.visx-chart").first();
  await expect(chart.locator(".visx-reference line")).toHaveCount(1);
  await chart.focus();
  await chart.press("Home");
  await chart.press("Enter");
  const chosen = new URL(page.url()).searchParams.get("timestamp")!;
  expect(chosen).not.toBe("2026-10-18T18:00:00");
  await expect(time).toHaveValue(chosen);
  await expect(page.getByRole("button",{name:"Дата",exact:true})).toHaveAttribute("data-date",chosen.slice(0,10));
  expect(new URL(page.url()).hash).toBe("#timeline");
  await expect(page.locator(".timeline-inspect")).toHaveCount(0);
  await expect(page.getByText(/Выберите точку кликом/)).toHaveCount(0);
  const x = await chart.locator(".visx-reference line").getAttribute("x1");
  const values = await time.locator("option:not([disabled])").evaluateAll(nodes=>nodes.map(n=>(n as HTMLOptionElement).value));
  await time.selectOption(values.at(-1)!);
  await expect(chart.locator(".visx-reference line")).not.toHaveAttribute("x1",x!);
  await page.reload();
  await expect(time).toHaveValue(values.at(-1)!);
  await expect(chart.locator(".visx-reference line")).toHaveCount(1);
  await selectDate(page,"2026-10-18");
  await time.selectOption("2026-10-18T12:00:00");
  await page.getByRole("slider",{name:"Конец видимого периода",exact:true}).focus();
  await page.getByRole("slider",{name:"Конец видимого периода",exact:true}).press("Home");
  await time.selectOption("2026-10-18T22:00:00");
  await expect.poll(async()=>{
    const line=Number(await chart.locator(".visx-reference line").getAttribute("x1"));
    const width=(await chart.boundingBox())!.width;
    return line>=66 && line<=width-20;
  }).toBe(true);
  await selectDate(page,"2026-08-01");
  await time.selectOption("2026-08-01T12:00:00");
  await expect(page.getByLabel("Конец периода",{exact:true})).toHaveValue("2026-08-01");
  await expect(chart.locator(".visx-reference line")).toHaveCount(1);
  const latest=(await page.locator(".timeline-kpi time").first().getAttribute("datetime"))!.slice(0,10);
  await page.getByRole("button",{name:"7 дней",exact:true}).click();
  await expect(page.getByLabel("Конец периода",{exact:true})).toHaveValue(latest);
  await expect(chart.locator(".visx-line").first()).toBeVisible();
  await expect(chart.locator(".visx-reference line")).toHaveCount(0);
});

test("station history also selects analysis time by clicking the graph", async ({page}) => {
  await page.goto("/?object=demo-ppd#timeline");
  const chart = page.locator(".timeline-charts svg.visx-chart").first();
  await expect(chart).toBeVisible();
  const box = (await chart.boundingBox())!;
  await chart.click({position:{x:box.width/2,y:70}});
  await expect.poll(() => new URL(page.url()).searchParams.get("timestamp")).toBeTruthy();
  const chosen = new URL(page.url()).searchParams.get("timestamp")!;
  await expect(page.getByLabel("Момент измерения",{exact:true})).toHaveValue(chosen);
  await expect(page.getByRole("button",{name:"Дата",exact:true})).toHaveAttribute("data-date",chosen.slice(0,10));
  expect(new URL(page.url()).hash).toBe("#timeline");
});

test('KPI units align in a row even when one value is missing',async({page})=>{
  await page.setViewportSize({width:1440,height:900});
  await page.goto('/?object=demo-ppd#timeline');
  await expect(page.locator('.timeline-kpi time').first()).toBeVisible();
  await expect(page.locator('.timeline-kpi .metric-empty')).toBeVisible();
  const positions=await page.locator('.timeline-kpi .metric-unit').evaluateAll(nodes=>nodes.map(n=>n.getBoundingClientRect().y));
  expect(positions).toHaveLength(4);
  expect(Math.max(...positions)-Math.min(...positions)).toBeLessThan(1);
});
