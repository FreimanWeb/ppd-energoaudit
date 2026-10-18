import {test,expect} from '@playwright/test';

for(const [route,selector] of [['overview','.station-kpis'],['timeline','.timeline-kpis']] as const)
  test(`${route} KPI values and info icons show nonempty explanations`,async({page})=>{
    await page.goto('/?object=demo-ppd#'+route);
    const cards=page.locator(selector+' .metric-card');
    await expect(cards).toHaveCount(4);
    for(const card of await cards.all()){
      await card.locator('strong').hover();
      const tip=page.locator('.explanation-tooltip[data-state="open"]');
      await expect(tip).toBeVisible();
      await expect(tip).toContainText(/\S/);
      await page.mouse.move(0,0);await page.keyboard.press('Escape');
      await card.locator('.tooltip-trigger').focus();
      await expect(tip).toBeVisible();
      await expect(tip).toContainText(/\S/);
      await page.keyboard.press('Escape');
    }
  });
