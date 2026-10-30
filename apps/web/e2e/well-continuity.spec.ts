import { test, expect } from "@playwright/test";

test("archive selection survives navigation and invalid selection is not replaced", async ({page}) => {
  await page.goto("/?object=demo-ppd&well=6&day=2026-10-18#well-history");
  const panel = page.locator(".well-history");
  await expect(panel.getByLabel("Нагнетательная скважина", {exact:true})).toHaveValue("6");
  await expect(panel.getByText("Качество и источники архива", {exact:true})).toBeVisible();
  await expect(panel.getByText("Дата текущего режима — дата выгрузки", {exact:false})).not.toBeVisible();
  const forecast = panel.getByRole("link", {name:"Прогноз по скважине · CRM",exact:true});
  await expect(forecast).toHaveAttribute("href", /well=6/);
  await expect(forecast).toHaveAttribute("href", /day=2026-10-18/);
  await page.goto("/?object=demo-ppd&well=missing#well-history");
  await expect(panel).toContainText("Скважина missing отсутствует в архиве этого объекта");
  await expect(panel.locator("svg.visx-chart")).toHaveCount(0);
  await expect(panel.getByLabel("Нагнетательная скважина", {exact:true})).toHaveValue("missing");
  await panel.getByLabel("Нагнетательная скважина", {exact:true}).selectOption("2");
  await expect(page).toHaveURL(/well=2/);
  await expect(panel.locator("svg.visx-chart")).toBeVisible();
});

test("network selection shares the well and carries context into its archive", async ({page}) => {
  const response=page.waitForResponse(r=>new URL(r.url()).pathname==="/api/objects/kns54an/network");
  await page.goto("/?object=kns54an&day=2026-09-29#network");
  const data=await (await response).json();
  const panel=page.getByRole("region",{name:"Схема водоводов",exact:true});
  const well=data.wells[1].well;
  await panel.scrollIntoViewIfNeeded();
  const beforeScroll=await page.evaluate(()=>window.scrollY);
  await panel.getByLabel("Найти скважину",{exact:true}).selectOption(well);
  expect(await page.evaluate(()=>window.scrollY)).toBeGreaterThanOrEqual(beforeScroll);
  await expect.poll(()=>new URL(page.url()).searchParams.get("well")).toBe(well);
  const archive=panel.getByRole("link",{name:"История и ГДИ",exact:true});
  expect(new URL(await archive.getAttribute("href")!,page.url()).searchParams.get("well")).toBe(well);
  await archive.click();
  await expect(page).toHaveURL(/#well-history$/);
  expect(new URL(page.url()).searchParams.get("day")).toBe("2026-09-29");
  await expect(page.getByLabel("Нагнетательная скважина",{exact:true})).toHaveValue(well);
});

test("CRM uses the selected well and monthly time control",async({page})=>{
  await page.goto("/?object=kns54an&well=2015#crm-wells");
  await expect(page.getByRole("heading",{name:/^Прогноз по скважинам · CRM/})).toBeVisible();
  const select=page.getByRole("combobox",{name:"Скважина",exact:true});
  await expect(select).toHaveValue("2015");
  const time=page.getByRole("region",{name:"Управление временем",exact:true});
  await expect(time.locator(".time-control-dates")).not.toContainText(/\d{2}:\d{2}/);
  await select.selectOption("2017");
  await expect.poll(()=>new URL(page.url()).searchParams.get("well")).toBe("2017");
  await page.goto("/?object=kns54an&well=missing#crm-wells");
  await expect(page.getByRole("combobox",{name:"Скважина",exact:true})).toHaveValue("missing");
  await expect(page.getByText(/Скважина missing отсутствует в этой выгрузке CRM/)).toBeVisible();
  await expect(page.locator("svg.visx-chart")).toHaveCount(0);
});

test("the initial archive well is carried into the other well tabs",async({page})=>{
  await page.goto("/?object=demo-ppd#well-history");
  await expect.poll(()=>new URL(page.url()).searchParams.get("well")).toBe("1");
  await page.getByRole("navigation",{name:"Вкладки: Скважины",exact:true}).getByRole("link",{name:/Прогноз по скважинам/}).click();
  expect(new URL(page.url()).searchParams.get("well")).toBe("1");
});

test("CRM month labels preserve source months despite a timezone offset",async({page})=>{
  const months=["2026-07-01T00:00:00+03:00","2026-08-01T00:00:00+03:00","2026-09-01T00:00:00+03:00"];
  await page.route("**/crm/well-runs/*/monthly?*",route=>route.fulfill({json:{
    series:months.map(month=>({month,base:1000,forecast:900,fact:1100})),
    downtime_marks:[],window:[months[0],months[2]],last:{forecast:900,fact:1100},
  }}));
  await page.goto("/?object=kns54an&well=2015#crm-wells");
  const time=page.getByRole("region",{name:"Управление временем",exact:true});
  await expect(time.locator(".time-control-dates")).toHaveText("июль 2026 г.сентябрь 2026 г.");
  await expect(page.locator("svg.visx-chart")).toHaveAttribute("data-time-domain",`${Date.parse("2026-07-01")},${Date.parse("2026-09-01")}`);
});

test("well loss rows lead to that well's archive before offering measures", async({page})=>{
  await page.goto("/?object=demo-ppd&aggregate=НА-1&day=2026-10-18#wells");
  const diagnostics=page.getByRole("region",{name:"Потери по скважинам",exact:true});
  const row=diagnostics.locator("tbody tr").first();
  const code=await row.locator("td").first().innerText();
  const archive=row.getByRole("link",{name:"История и ГДИ",exact:true});
  expect(new URL(await archive.getAttribute("href")!,page.url()).searchParams.get("well")).toBe(code);
  const actions=page.getByRole("region",{name:"Мероприятия участка",exact:true});
  expect((await actions.boundingBox())!.y).toBeGreaterThan((await diagnostics.boundingBox())!.y);
  await archive.click();
  await expect(page.getByLabel("Нагнетательная скважина",{exact:true})).toHaveValue(code);
});
