import { test,expect,type Page } from '@playwright/test';
async function fixture(page:Page){
 await page.goto('/');
 await page.getByLabel('Объект',{exact:true}).selectOption('kns54an');
 await page.getByLabel('Агрегат',{exact:true}).selectOption('НА-1');
 await page.getByLabel('Дата',{exact:true}).selectOption('2026-09-29');
 await expect(page.getByText('600',{exact:true}).first()).toBeVisible();
}
test('power telemetry is a held state, and formula fractions have full accessible math layout',async({page})=>{
 await fixture(page);
 await page.locator('nav a[href="#telemetry"]').click();
 await expect.poll(()=>page.locator('.js-plotly-plot').count()).toBeGreaterThan(0);
 await expect.poll(()=>page.evaluate(()=>{
  const plots=[...document.querySelectorAll('.js-plotly-plot')] as (HTMLElement&{data?:{line?:{shape?:string}}[];layout?:{yaxis?:{title?:{text?:string}}}})[];
  return plots.find(p=>p.layout?.yaxis?.title?.text==='кВт')?.data?.[0]?.line?.shape;
 })).toBe('hv');
 await page.locator('nav a[href="#formulas"]').click();
 await expect(page.locator('.formula-card .katex-display').first()).toBeVisible();
 await expect.poll(()=>page.locator('.formula-card math mfrac').count()).toBeGreaterThan(0);
 await expect.poll(()=>page.locator('.formula-card math msub').count()).toBeGreaterThan(0);
});
test('scenario measures retain energy benefit but never claim known capital or payback',async({page})=>{
 await fixture(page);
 await page.locator('nav a[href="#measures"]').click();
 const annual=page.getByRole('row').filter({hasText:'сценарная оценка'}).first();
 await expect(annual).toBeVisible();
 await expect(annual.getByRole('cell').nth(4)).toHaveText('Требует оценки');
 await expect(annual.getByRole('cell').nth(5)).toHaveText('Требует оценки');
 await page.getByLabel('Основание расчёта').selectOption('forecast');
 await expect(page.getByLabel('Мероприятие денежного потока')).toBeVisible();
 await page.getByLabel('Мероприятие денежного потока').selectOption('efficiency_recovery_scenario');
 await expect(page.locator('.page-kpis strong').filter({hasText:'Требует оценки'})).toHaveCount(4);
 await expect(page.locator('main')).toContainText('CAPEX требует оценки; линия окупаемости не построена.');
});
