import { test, expect } from '@playwright/test';

test('machine block owns pump parameters and remains readable on mobile', async ({page}) => {
  await page.goto('/?object=kns54an&aggregate=НА-1&mode=field_trip#overview');
  await expect(page.locator('.pump-regime-card')).toHaveCount(0);
  await page.getByRole('link',{name:'Открыть машинный блок',exact:true}).click();
  const panel=page.locator('.page-panel').filter({has:page.getByRole('heading',{name:'Режим машинного блока',exact:true})});
  await expect(panel).toContainText('Напор');
  await expect(panel).toContainText('Подача');
  await expect(panel).toContainText('Электрическая мощность');
  await expect(panel).toContainText('Гидравлическая мощность');
  for (const width of [1800,1280,390]) {
    await page.setViewportSize({width,height:1000});
    await expect(panel).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.getByLabel('Агрегат',{exact:true}).selectOption('НА-2');
  await expect(page.getByRole('heading',{name:'Режим машинного блока',exact:true})).toBeVisible();
  await expect(page.locator('.overview-page')).toContainText('УРЭ выбранного агрегата НА-2');
});
