import { test, expect } from '@playwright/test';

test('CRM comparison excludes dates not shared by forecast and fact', async ({ page }) => {
  await page.route('**/crm/runs/*', route => route.fulfill({ json: {
    interval_hours: 24, by_unit: { 'НА-1': [['2026-09-01', 1000], ['2026-09-02', 10], ['2026-09-03', 30]] },
    total: [['2026-09-01', 1000], ['2026-09-02', 10], ['2026-09-03', 30]], partial_days: [], model: 'fixture', events: false,
  } }));
  await page.route('**/crm/fact?*', route => route.fulfill({ json: {
    series: [{ aggregate: 'НА-1', points: [['2026-09-02', 0], ['2026-09-03', 20], ['2026-09-04', 9999]] }],
  } }));
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29#crm');
  await expect(page.locator('.metric-card').filter({ has: page.getByText('Прогноз на общих датах', { exact: true }) }).locator('strong')).toHaveText('20');
  await expect(page.locator('.metric-card').filter({ has: page.getByText('Факт на общих датах', { exact: true }) }).locator('strong')).toHaveText('10');
  await expect(page.getByText(/суток с данными: 2/)).toBeVisible();
});

test('empty filter intersection clears the object and calculations and can be reset', async ({ page }) => {
  await page.route('**/catalog/objects', async route => {
    const response = await route.fetch();
    const objects = await response.json();
    const first = objects.find((object: { code: string }) => object.code === 'kns54an');
    await route.fulfill({ response, json: [
      { ...first, ngdu_name: 'А', water_type: 'агрессивная' },
      { ...first, code: 'another', name: 'Другой объект', ngdu_name: 'Б', water_type: 'пресная' },
    ] });
  });
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29#overview');
  await expect(page.locator('main').getByText('600', { exact: true }).first()).toBeVisible();
  await page.locator('details.object-filter').filter({ hasText: 'НГДУ' }).locator('summary').click();
  await page.getByRole('checkbox', { name: 'НГДУ: А', exact: true }).check();
  await page.locator('details.object-filter').filter({ hasText: 'Тип воды' }).locator('summary').click();
  await page.getByRole('checkbox', { name: 'Тип воды: пресная', exact: true }).check();
  await expect(page.getByLabel('Объект', { exact: true })).toBeDisabled();
  await expect(page.getByText(/Нет объектов с выбранными фильтрами/)).toBeVisible();
  await expect(page.locator('main').getByText('600', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Сбросить фильтры', exact: true }).click();
  await expect(page.getByLabel('Объект', { exact: true })).toHaveValue('kns54an');
  await expect(page.locator('main').getByText('600', { exact: true }).first()).toBeVisible();
});
