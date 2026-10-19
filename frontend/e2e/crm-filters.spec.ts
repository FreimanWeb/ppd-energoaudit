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
