import { test, expect } from '@playwright/test';

test('loss presentation switches between decomposition and percentage without changing data', async ({ page }) => {
  await page.route('**/snapshot-audit', async route => {
    const response = await route.fetch();
    const audit = await response.json();
    audit.losses = [
      { name: 'Полезная мощность', power_kw: 300, share: .5, category: 'полезная' },
      { name: 'Потери двигателя', power_kw: 120, share: .2, category: 'потеря' },
      { name: 'Потери передачи', power_kw: 190, share: 190 / 600, category: 'потеря' },
      { name: 'Коррекция', power_kw: -10, share: -10 / 600, category: 'потеря' },
    ];
    await route.fulfill({ response, json: audit });
  });
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29#machine-losses');
  const panel = page.locator('.page-panel').filter({has: page.getByRole('heading', {name: /^Цифровая карта потерь мощности/})});
  const plot = panel.getByRole('group', { name: 'Декомпозиция мощности', exact: true });
  await expect(panel.locator('.plot-wrap')).toHaveCount(1);
  const motor = plot.getByRole('button', { name: /^Потери в электродвигателе:/ });
  const transmission = plot.getByRole('button', { name: /^Потери в передаче:/ });
  await motor.hover();
  await expect(plot.locator('.visx-bar.is-active')).toHaveCount(1);
  await expect(plot.getByRole('status')).toContainText('Потери в электродвигателе');
  await expect(plot.getByRole('status').locator('b')).toHaveText('120 кВт');
  await expect(plot.getByRole('status')).not.toContainText('Потери в передаче');
  await expect(plot.getByRole('status').locator('strong')).toHaveText('Потери в электродвигателе');
  await expect(plot.getByRole('status').locator('.chart-tooltip-share')).toHaveText('20 %');
  await expect(motor).toHaveAttribute('stroke', 'transparent');
  await transmission.hover();
  await expect(plot.locator('.visx-bar.is-active')).toHaveCount(1);
  await expect(plot.getByRole('status').locator('b')).toHaveText('190 кВт');
  await expect(motor).not.toHaveClass(/is-active/);
  await page.getByText('Таблица составляющих', { exact: true }).click();
  const tableBefore = await panel.locator('table').innerText();
  await panel.getByRole('button', { name: 'Структура, %', exact: true }).click();
  await expect(page.getByText(/Для режима с отрицательными коррекциями/)).toBeVisible();
  await expect(panel.locator('.plot-wrap')).toHaveCount(0);
  expect(await panel.locator('table').innerText()).toBe(tableBefore);
  await panel.getByRole('button', { name: 'Разложение', exact: true }).click();
  await expect(plot).toBeVisible();
  await expect(panel.locator('svg.visx-flow')).toHaveCount(0);
  await plot.getByRole('button', { name: /^Коррекция:/ }).hover();
  await expect(plot.getByRole('status').locator('b')).toHaveText('-10 кВт');
});

test('percentage structure uses original shares and fixes the axis at 100 percent', async ({ page }, testInfo) => {
  let excess = false;
  await page.route('**/snapshot-audit', async route => {
    const response = await route.fetch();
    const audit = await response.json();
    audit.audit.metrics.p_electric_kw = 100;
    audit.losses = [
      { name: 'Полезная мощность', power_kw: excess ? 80 : 60, share: excess ? .8 : .6, category: 'полезная' },
      { name: 'Потери двигателя', power_kw: 30, share: .3, category: 'потеря' },
    ];
    await route.fulfill({ response, json: audit });
  });
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29#machine-losses');
  const panel = page.locator('.page-panel').filter({has: page.getByRole('heading', {name: /^Цифровая карта потерь мощности/})});
  await panel.getByRole('button', { name: 'Структура, %', exact: true }).click();
  const plot = panel.getByRole('group', { name: 'Структура мощности, %', exact: true });
  await expect(plot.locator('svg.visx-chart')).toBeVisible();
  await expect(plot.locator('.visx-axis-x').getByText('100', { exact: true })).toBeVisible();
  await plot.getByRole('button', { name: /^Полезная гидравлическая мощность:/ }).hover();
  await expect(plot.getByRole('status').locator('b')).toHaveText('60 кВт');
  await expect(page.getByText('Показанные составляющие: 90% потреблённой мощности.')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('percentage-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 320, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('percentage-mobile.png'), fullPage: true });
  excess = true;
  await page.reload();
  await panel.getByRole('button', { name: 'Структура, %', exact: true }).click();
  await expect(page.getByText(/Сумма составляющих превышает 100%/)).toBeVisible();
  await expect(panel.locator('.plot-wrap')).toHaveCount(0);
});
