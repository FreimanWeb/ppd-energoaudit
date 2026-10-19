import { test, expect } from "@playwright/test";

test("scheme shows report groups as consumption shares below equipment", async ({page}) => {
  await page.setViewportSize({width:1440,height:1000});
  const response = page.waitForResponse(r => r.url().endsWith("/station-summary"));
  await page.goto("/?object=demo-ppd&aggregate=НА-1&mode=field_trip#overview");
  const balance = (await (await response).json()).network;
  const scheme = page.getByRole("region",{name:"Условная технологическая схема ППД",exact:true});
  const markers = page.locator(".loss-flow-stage");
  await expect(markers).toHaveCount(3);
  await expect(page.locator(".scheme-loss-summary")).toHaveCount(0);
  const hall = balance.operator_balance.groups.find((group:{id:string})=>group.id === "hall").power_kw;
  const pct = new Intl.NumberFormat("ru-RU",{maximumFractionDigits:1}).format(hall/balance.input_kw*100);
  await expect(markers.first().locator(".loss-flow-parent .loss-flow-share")).toHaveText(`${pct} % потребления`);
  await expect(scheme).toContainText("100 % — потреблённая мощность");
  for (const width of [1800,1280,390]) {
    await page.setViewportSize({width,height:1000});
    await expect(scheme.locator("svg").getByRole("button")).toHaveCount(0);
    await expect(scheme.locator(".loss-flow-toggle")).toHaveCount(3);
    expect(await page.evaluate(() => document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  await expect(page.getByLabel("Агрегат",{exact:true})).toHaveCount(0);
  await page.reload();
  await expect(markers).toHaveCount(3);
});

test("unavailable balance never shows invented percentages", async ({page}) => {
  await page.route("**/station-summary", async route => {
    const response = await route.fetch();
    const summary = await response.json();
    await route.fulfill({response,json:{...summary,network:{status:"infeasible",warnings:[]}}});
  });
  await page.goto("/?object=demo-ppd&aggregate=НА-1&mode=field_trip#overview");
  await expect(page.locator(".scheme-panel")).toContainText("Доли потерь недоступны");
  await expect(page.locator(".loss-flow-parent .loss-flow-value")).toHaveText(["Нет оценки","Нет оценки","Нет оценки"]);
  await expect(page.locator(".station-kpis .metric-card").filter({hasText:"Потери до устьев · оценка"}).locator("strong")).toHaveText("Нет данных");
});

test('conditional scheme groups wells, has no duplicated cards, and links hover and keyboard focus',async({page})=>{
  await page.goto('/?object=demo-ppd#overview');
  const scheme=page.getByRole('region',{name:'Условная технологическая схема ППД',exact:true});
  await expect(scheme).toBeVisible();
  await expect(scheme.locator('.scheme-loss-summary')).toHaveCount(0);
  await expect(scheme.locator('.well-group-count')).toHaveText('В расчёте: 6 скважин');
  for(const id of ['hall','pipes','wells']){
    const area=scheme.locator(`.scheme-area-link[data-stage="${id}"]`);
    const card=scheme.locator(`.loss-flow-stage[data-stage="${id}"]`);
    await expect(area.locator('rect')).toHaveCSS('stroke','rgb(229, 231, 235)');
    await card.hover();
    await expect(area).toHaveAttribute('data-active','true');
    await expect(card).toHaveAttribute('data-active','true');
    await area.hover();
    await expect(card).toHaveAttribute('data-active','true');
    await page.mouse.move(0,0);
    await area.focus();
    await expect(card).toHaveAttribute('data-active','true');
    await expect(area).toHaveAttribute('data-active','true');
    await area.press('Tab');
    await page.locator('.page-heading h1').click();
  }
});
