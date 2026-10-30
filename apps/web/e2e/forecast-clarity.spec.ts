import { test, expect } from '@playwright/test';

test('aggregate forecast selects a usable period and explains dates and method', async ({ page }) => {
  await page.goto('/?object=kns54an&aggregate=НА-1#forecast');
  await expect(page.getByRole('heading', { name: /^Прогноз закачки НА/ })).toBeVisible();
  await expect(page.getByText('НА-1 · линейная экстраполяция измеренных объёмов', { exact: true })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Факт и прогноз закачки', exact: true })).toBeVisible();
  await expect(page.getByLabel('Периодичность')).toHaveValue('30');
  await page.getByLabel('Начало периода').fill('2026-09-01');
  await expect(page.getByLabel('Периодичность')).toHaveValue('7');
  await expect(page.getByText(/Автоматически выбраны периоды по 7 суток/)).toBeVisible();
  await expect(page.getByTestId('forecast-calendar')).toContainText(/История: .*Прогноз:/);
  await page.getByLabel('Начало периода').fill('2026-07-01');
  await expect(page.getByLabel('Периодичность')).toHaveValue('30');
  await page.getByLabel('Начало периода').fill('2026-09-01');
  await expect(page.getByLabel('Периодичность')).toHaveValue('7');

  await page.getByLabel('Периодичность').selectOption('30');
  await expect(page.getByText('Недостаточно истории для выбранной длины периода', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Использовать периоды по 7 суток', exact: true }).click();
  await expect(page.getByRole('group', { name: 'Факт и прогноз закачки', exact: true })).toBeVisible();
});

test('short history has a useful empty state without fabricated forecast', async ({ page }) => {
  await page.goto('/?object=kns54an&aggregate=НА-1#forecast');
  await expect(page.getByRole('group', { name: 'Факт и прогноз закачки', exact: true })).toBeVisible();
  await page.getByLabel('Начало периода').fill('2026-09-29');
  await page.getByLabel('Конец периода').fill('2026-09-29');
  await expect(page.getByText('Недостаточно истории для выбранной длины периода', { exact: true })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Факт и прогноз закачки', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Вся доступная история', exact: true }).click();
  await expect(page.getByRole('group', { name: 'Факт и прогноз закачки', exact: true })).toBeVisible();
});

test('aggregate without telemetry offers importing history rather than requesting a forecast', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', request => { if (new URL(request.url()).pathname.endsWith('/forecast')) requests.push(request.url()); });
  await page.goto('/?object=kns97pren&aggregate=НА-2 ПР#forecast');
  await expect(page.getByText('Для выбранного НА нет истории телеметрии. Импортируйте суточные объёмы закачки, чтобы построить прогноз.', { exact: true })).toBeVisible();
  expect(requests).toHaveLength(0);
});

test('instantaneous demo flow is not presented as measured daily injection', async ({ page }) => {
  await page.goto('/?object=demo-ppd&aggregate=НА-1#forecast');
  await expect(page.getByText('Записи мгновенного расхода не заменяют измеренные суточные объёмы закачки.', { exact: true })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Факт и прогноз закачки', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Проверить телеметрию', exact: true })).toHaveAttribute('href', '#telemetry');
});
