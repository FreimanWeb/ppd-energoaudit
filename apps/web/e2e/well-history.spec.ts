import { test, expect } from "@playwright/test";

test("demo well history includes synthetic pressures and studies without an import", async ({page}) => {
  await page.goto("/?object=demo-ppd#well-history");
  const panel = page.locator(".well-history");
  await expect(panel.getByRole("combobox").locator("option")).toHaveCount(6);
  await expect(panel).toContainText("Демонстрационные данные");
  await expect(panel.locator(".visx-line")).toHaveCount(2);
  const control = panel.getByRole("region", {name:"Управление временем",exact:true});
  await expect(control).toBeVisible();
  await expect(control.locator(".time-control-dates")).not.toContainText(/\d{2}:\d{2}/);
  await expect(control.getByRole("slider", {name:"Конец видимого периода",exact:true})).toHaveAttribute("step", "1");
  const chart = panel.locator("svg.visx-chart");
  const fullDomain = await chart.getAttribute("data-time-domain");
  await control.getByRole("slider", {name:"Конец видимого периода",exact:true}).focus();
  await control.getByRole("slider", {name:"Конец видимого периода",exact:true}).press("ArrowLeft");
  await expect(chart).not.toHaveAttribute("data-time-domain", fullDomain!);
  const previousMonth = new Date(Number(fullDomain!.split(",")[1]));
  previousMonth.setUTCMonth(previousMonth.getUTCMonth() - 1);
  await expect(chart).toHaveAttribute("data-time-domain", `${fullDomain!.split(",")[0]},${previousMonth.getTime()}`);
  await control.getByRole("button", {name:"Весь период",exact:true}).click();
  await expect(chart).toHaveAttribute("data-time-domain", fullDomain!);
  await expect(panel).not.toContainText("История скважин для объекта ещё не импортирована");
  await panel.getByRole("combobox").selectOption("6");
  await expect(panel.getByRole("combobox")).toHaveValue("6");
  await panel.getByText("ГДИ: история исследований (6 записей)", {exact:true}).click();
  await expect(panel.getByRole("cell", {name:"КВД",exact:true})).toHaveCount(6);
});

test("well history is available without a pump snapshot and preserves monthly units", async ({page}) => {
  await page.route("**/objects/kns54an/wells", route => route.fulfill({json:{
    wells:[{code:"4623А",latest_at:"2026-10-14",current_at:"2026-10-14"}],
    density_default:{density_kgm3:1138,available_from:"2026-10-16",source:"Сообщение источника"},
  }}));
  await page.route("**/objects/kns54an/wells/*/history", route => route.fulfill({json:{
    well_code:"4623А", warnings:["Давления в исходных атм, дата измерения текущего режима не подтверждена."],
    records:["p_well","p_bg"].flatMap(metric => ["2024-01-01","2024-02-01","2024-03-01","2024-04-01"].map((observed_at,index) => ({
      observed_at,grain:"month",record_kind:"monthly_actual",metric,value:(metric === "p_bg" ? 130 : 100)+index,
      unit:"атм",study_type:"",source_file:"source.xls",source_sheet:"Динамика",source_row:6+index,
      exported_at:"2026-10-14",
    }))),
  }}));
  await page.goto("/?object=kns54an&aggregate=НА-1&day=2026-10-01#well-history");
  const panel = page.locator(".page-panel").filter({has:page.getByRole("heading",{name:"История нагнетательных скважин",exact:true})});
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("combobox")).toHaveValue("4623А");
  await expect(panel).toContainText("атм");
  await expect(panel.locator("svg.visx-chart")).toBeVisible();
  const lines = panel.locator(".visx-line");
  await expect(lines).toHaveCount(2);
  for (const name of ["Давление на устье", "Давление на БГ"]) {
    const line = panel.locator(`.visx-line[name="${name}"]`);
    await expect(line).toHaveAttribute("d", /L/);
    await expect(line.locator("..").locator("circle")).toHaveCount(4);
  }
  const control = panel.getByRole("region", {name:"Управление временем",exact:true});
  await expect(control.locator(".time-control-dates")).toHaveText("январь 2024 г.апрель 2024 г.");
  const end = control.getByRole("slider", {name:"Конец видимого периода",exact:true});
  await end.focus();
  await end.press("Home");
  const chart = panel.locator("svg.visx-chart");
  const range = (start:string, finish:string) => `${Date.parse(start)},${Date.parse(finish)}`;
  await expect(chart).toHaveAttribute("data-time-domain", range("2024-01-01", "2024-02-01"));
  const band = control.getByRole("slider", {name:"Положение видимого периода",exact:true});
  await band.focus();
  await band.press("ArrowRight");
  await expect(chart).toHaveAttribute("data-time-domain", range("2024-02-01", "2024-03-01"));
  await band.press("End");
  await expect(chart).toHaveAttribute("data-time-domain", range("2024-03-01", "2024-04-01"));
  await control.getByRole("button", {name:"Весь период",exact:true}).click();
  const box = await end.boundingBox();
  await page.mouse.move(box!.x + box!.width - 6, box!.y + 12);
  await page.mouse.down();
  await page.mouse.move(box!.x + box!.width * .48, box!.y + 12, {steps:5});
  await page.mouse.up();
  const endDate = new Date(Number((await chart.getAttribute("data-time-domain"))!.split(",")[1]));
  expect(endDate.getUTCDate()).toBe(1);
  expect(endDate.getUTCHours()).toBe(0);
  expect(endDate.getUTCMonth()).toBeLessThan(3);
  await page.setViewportSize({width:320,height:844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});
