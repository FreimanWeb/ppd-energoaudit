import { test, expect } from '@playwright/test';

async function efficiency(page: import('@playwright/test').Page, actual: number|null, nominal: number|null, status='assumptions') {
  await page.route('**/snapshot-audit', async route => {
    const response=await route.fetch(), audit=await response.json();
    Object.assign(audit.audit.metrics,{eta_unit:actual,eta_nom:nominal});
    audit.quality.status=status;
    await route.fulfill({response,json:audit});
  });
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29#overview');
  const panel=page.locator('.page-panel').filter({has:page.getByRole('heading',{name:'КПД',exact:true})});
  await expect(panel).toBeVisible();
  return panel;
}

test('efficiency uses two values and a point difference without a traffic light',async({page})=>{
  const panel=await efficiency(page,.611,.704);
  await expect(panel.locator('.metric-segment')).toHaveCount(2);
  await expect(panel.locator('.metric-segment strong')).toHaveText(['61,1', '70,4']);
  await expect(panel.locator('.metric-segment .metric-unit')).toHaveText(['%', '%']);
  await expect(panel.locator('.metric-segment').first().locator('sup')).toHaveText('↓9,3');
  await expect(panel.getByLabel('Разница КПД')).toHaveCSS('position', 'absolute');
  await expect(panel.getByLabel('Разница КПД')).toHaveCSS('color', 'rgb(217, 45, 32)');
  await expect(panel.locator('p.efficiency-difference')).toHaveCount(0);
  await expect(panel.getByText('Светофор КПД',{exact:true})).toHaveCount(0);
  await expect(panel.locator('.gauge-chart')).toHaveCount(0);
  await panel.getByText('Диагностика агрегата',{exact:true}).click();
  await expect(panel.getByText('Коэф. загрузки ЭД',{exact:true})).toBeVisible();
  await expect(panel.getByLabel('Разобрать: КПД агрегата',{exact:true})).toBeVisible();
});

test('a positive difference keeps its sign',async({page})=>{
  const panel=await efficiency(page,.9,.8);
  await expect(panel.getByLabel('Разница КПД')).toHaveText('↑10');
});

for (const [actual,nominal,status] of [[null,.8,'assumptions'],[1.2,.8,'assumptions'],[.6,null,'assumptions'],[.6,.8,'unfit'],[.8,.8,'assumptions'],[.6,0,'assumptions']] as const)
  test(`efficiency omits unsupported or zero difference ${actual}/${nominal}/${status}`,async({page})=>{
    const panel=await efficiency(page,actual,nominal,status);
    await expect(panel.getByLabel('Разница КПД')).toHaveCount(0);
    await expect(panel.locator('.gauge-chart')).toHaveCount(0);
  });
