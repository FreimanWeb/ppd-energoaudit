import { test, expect } from "@playwright/test";

test("well history is available without a pump snapshot and preserves monthly units", async ({page}) => {
  await page.route("**/objects/kns54an/wells", route => route.fulfill({json:{
    wells:[{code:"4623А",latest_at:"2026-10-14",current_at:"2026-10-14"}],
    density_default:{density_kgm3:1138,available_from:"2026-10-16",source:"Сообщение источника"},
  }}));
  await page.route("**/objects/kns54an/wells/*/history", route => route.fulfill({json:{
    well_code:"4623А", warnings:["Давления в исходных атм, дата измерения текущего режима не подтверждена."],
    records:["2026-08-01","2026-09-01"].map((observed_at,index) => ({
      observed_at,grain:"month",record_kind:"monthly_actual",metric:"p_well",value:100+index,
      unit:"атм",study_type:"",source_file:"source.xls",source_sheet:"Динамика",source_row:6+index,
      exported_at:"2026-10-14",
    })),
  }}));
  await page.goto("/?object=kns54an&aggregate=НА-1&day=2026-10-01#well-history");
  const panel = page.locator(".page-panel").filter({has:page.getByRole("heading",{name:"История нагнетательных скважин",exact:true})});
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("combobox")).toHaveValue("4623А");
  await expect(panel).toContainText("атм");
  await expect(panel.locator("svg.visx-chart")).toBeVisible();
  await page.setViewportSize({width:320,height:844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});
