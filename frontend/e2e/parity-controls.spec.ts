import { test, expect, type Page } from '@playwright/test';

async function fixture(page: Page) {
  await page.goto('/');
  await page.getByLabel('Объект', { exact: true }).selectOption('kns54an');
  await page.getByLabel('Агрегат', { exact: true }).selectOption('НА-1');
  await page.getByLabel('Дата', { exact: true }).selectOption('2026-09-29');
  await expect(page.getByText('600', { exact: true }).first()).toBeVisible();
}
async function section(page: Page, hash: string) {
  await page.locator(`nav a[href="#${hash}"]`).click();
}

test('water and NGDU filters actually constrain selectable objects and reset safely', async ({ page }) => {
  await fixture(page);
  const all = await page.getByLabel('Объект', { exact: true }).locator('option').count();
  await page.locator('.object-filter').filter({ hasText: 'Тип воды' }).locator('summary').click();
  await page.getByLabel('Тип воды: пресная', { exact: true }).check();
  await expect(page.getByLabel('Объект', { exact: true }).locator('option[value="kns54an"]')).toHaveCount(0);
  expect(await page.getByLabel('Объект', { exact: true }).locator('option').count()).toBeLessThan(all);
  await page.getByLabel('Тип воды: пресная', { exact: true }).uncheck();
  await page.locator('.object-filter').filter({ hasText: 'НГДУ' }).locator('summary').click();
  await page.getByLabel('НГДУ: Азнакаевскнефть', { exact: true }).check();
  await expect(page.getByLabel('Объект', { exact: true }).locator('option[value="kns97pren"]')).toHaveCount(0);
  await expect(page.getByLabel('Объект', { exact: true }).locator('option[value="kns54an"]')).toHaveCount(1);
  await page.getByLabel('НГДУ: Азнакаевскнефть', { exact: true }).uncheck();
  await expect(page.getByLabel('Объект', { exact: true }).locator('option')).toHaveCount(all);
});

test('calendar statuses distinguish valid and unfit days and changing month can select history', async ({ page }) => {
  await fixture(page);
  await page.getByText('Календарь пригодности данных', { exact: true }).click();
  await expect(page.getByRole('button', { name: '2026-09-29: Пригодные сутки', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '2026-09-30: Непригодные данные', exact: true }).click();
  await expect(page.getByLabel('Дата', { exact: true })).toHaveValue('2026-09-30');
  await expect(page.getByText('Данные непригодны для достоверных выводов')).toBeVisible();
  await page.getByLabel('Месяц календаря').fill('2026-07');
  await page.getByRole('button', { name: '2026-07-01: Пригодные сутки', exact: true }).click();
  await expect(page.getByLabel('Дата', { exact: true })).toHaveValue('2026-07-01');
  await expect(page.getByLabel('Момент измерения')).toHaveValue('2026-07-01T23:30:00');
  await expect(page.getByRole('button', { name: '2026-07-01: Пригодные сутки', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

test('forecast periodicity uses legacy defaults and preserves history before zero', async ({ page }) => {
  await fixture(page);
  await section(page, 'forecast');
  await expect(page.getByLabel('Горизонт прогноза')).toHaveValue('36');
  await page.getByLabel('Периодичность').selectOption('7');
  await expect(page.getByLabel('Горизонт прогноза')).toHaveValue('52');
  await page.getByLabel('Периодичность').selectOption('1');
  await expect(page.getByLabel('Горизонт прогноза')).toHaveValue('1095');
  await page.getByLabel('Горизонт прогноза').fill('1500');
  const plot = page.locator('.js-plotly-plot').first();
  await expect.poll(async () => plot.evaluate(el => {
    const data = (el as HTMLElement & { data?: { name: string; x: number[] }[] }).data;
    return data?.find(t => t.name === 'Прогноз')?.x.at(-1);
  })).toBe(1500);
  expect(await plot.evaluate(el => {
    const data = (el as HTMLElement & { data: { name: string; x: number[] }[] }).data;
    return data.find(t => t.name === 'Факт')!.x[0];
  })).toBeLessThan(0);
  await page.getByLabel('Периодичность').selectOption('30');
  await expect(page.getByLabel('Горизонт прогноза')).toHaveValue('36');
});

test('no telemetry object stays honest in analysis and field trip uses measured passport values', async ({ page }) => {
  await fixture(page);
  await page.getByLabel('Объект', { exact: true }).selectOption('kns97pren');
  await expect(page.getByLabel('Дата', { exact: true })).toBeDisabled();
  await expect(page.locator('main')).toContainText(/нет.*телеметр|нет дат/i);
  await expect(page.getByText('600', { exact: true })).toHaveCount(0);
  await page.getByLabel('Агрегат', { exact: true }).selectOption('НА-2 ПР');
  await page.getByLabel('Режим', { exact: true }).selectOption('field_trip');
  await expect(page.getByRole('heading', { name: 'Паспорт и исходный режим' })).toBeVisible();
  await expect(page.locator('main')).toContainText('Выезд');
  await expect(page.locator('main')).toContainText('189');
  await expect(page.locator('main')).toContainText('40,25');
  await expect(page.locator('main')).toContainText('9,6');
  await expect(page.getByLabel('Дата', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('alert')).toHaveCount(0);
  await section(page, 'working-point');
  await expect(page.locator('.js-plotly-plot').first()).toBeVisible();
});

test('onboarding exposes readiness and both read-only templates for the actual selected aggregate', async ({ page }) => {
  await fixture(page);
  await section(page, 'onboarding');
  await expect(page.getByRole('heading', { name: 'Готовность выбранного агрегата' })).toBeVisible();
  await expect(page.locator('main table').last()).toContainText('Есть');
  await page.getByText('Шаблон паспорта объекта', { exact: true }).click();
  await expect(page.locator('pre').first()).toContainText('aggregates');
  await page.getByText('Шаблон записи для верификации', { exact: true }).click();
  await expect(page.locator('pre').last()).toContainText('config/verification.yaml');
  await expect(page.locator('main input, main textarea')).toHaveCount(0);
});

test('a chosen measurement remains shared across sources, formulas and scheme zoom controls', async ({ page }) => {
  await fixture(page);
  const auditResponse = page.waitForResponse(r => r.url().endsWith('/snapshot-audit') && r.request().postDataJSON()?.timestamp === '2026-09-29T12:00:00');
  await page.getByLabel('Момент измерения').selectOption('2026-09-29T12:00:00');
  expect((await auditResponse).status()).toBe(200);
  await section(page, 'sources');
  await expect(page.locator('main')).toContainText('e2e-scada.csv');
  await expect(page.locator('.header-tag')).toContainText('12:00:00');
  await section(page, 'formulas');
  await expect(page.locator('.formula-card').first()).toBeVisible();
  await expect(page.getByLabel('Момент измерения')).toHaveValue('2026-09-29T12:00:00');
  await section(page, 'scheme');
  await expect(page.getByLabel('Выбранное оборудование')).toContainText('600');
  await page.getByLabel('Увеличить схему').click();
  await expect(page.locator('.scheme-tools')).toContainText('120%');
  await page.getByRole('button', { name: 'По размеру', exact: true }).click();
  await expect(page.locator('.scheme-tools')).toContainText('100%');
  await page.getByLabel('Уменьшить схему').click();
  await expect(page.locator('.scheme-tools')).toContainText('83%');
  await expect(page.getByLabel('Момент измерения')).toHaveValue('2026-09-29T12:00:00');
});

test('CRM scenario and aggregate choice change the true predicted series and graph click selects a well', async ({ page }) => {
  await fixture(page);
  await section(page, 'crm');
  await page.getByLabel('Сценарий CRM').selectOption('baseline');
  const plot = page.locator('.js-plotly-plot').first();
  const predicted = async () => plot.evaluate(el =>
    (el as HTMLElement & { data?: { name: string; y: number[] }[] }).data?.find(t => t.name === 'Прогноз CRM')?.y[0]);
  await expect.poll(predicted).toBe(5760);
  await page.getByLabel('Показатель CRM').selectOption('НА-1');
  await expect.poll(predicted).toBe(2880);
  await page.getByLabel('Сценарий CRM').selectOption('event');
  await expect.poll(predicted).toBe(4800);
  await page.getByLabel('Показатель CRM').selectOption('НА-1');
  await expect.poll(predicted).toBe(2400);
  await section(page, 'crm-wells');
  const graph = page.locator('.js-plotly-plot').last();
  await expect(graph.locator('.scatterlayer .trace:last-child .point').first()).toBeVisible();
  await graph.locator('.scatterlayer .trace:last-child .point').first().scrollIntoViewIfNeeded();
  const point = await graph.locator('.scatterlayer .trace:last-child .point').first().boundingBox();
  expect(point).not.toBeNull();
  await page.mouse.click(point!.x + point!.width / 2, point!.y + point!.height / 2);
  await expect(page.getByLabel('Скважина графа')).not.toHaveValue('');
  await expect(page.locator('main')).toContainText('Связанная скважина');
});

test('CRM graph preserves downtime square markers from the legacy wells view', async ({ page }) => {
  await fixture(page);
  await section(page, 'crm-wells');
  const graph = page.locator('.js-plotly-plot').last();
  await expect.poll(async () => graph.evaluate(el => {
    const node = (el as HTMLElement & { data?: { mode: string; text: string[]; marker: { symbol?: string[] } }[] }).data?.find(t => t.mode.includes('markers') && t.mode.includes('text'));
    const index = node?.text.indexOf('2017') ?? -1;
    return index < 0 ? undefined : node?.marker.symbol?.[index];
  })).toBe('square');
});

test('selected pump exposes the legacy engineering assessment alongside pressures', async ({ page }) => {
  await fixture(page);
  await section(page, 'scheme');
  const equipment = page.getByLabel('Выбранное оборудование');
  await expect(equipment).toContainText(/КПД.*факт|Фактический КПД/i);
  await expect(equipment).toContainText(/КПД.*ном|Номинальный КПД/i);
  await expect(equipment).toContainText(/загрузк|K_з|Kз/i);
  await expect(equipment).toContainText(/УРЭ|Удельный расход/i);
  await expect(equipment).toContainText(/потери.*КПД|Потери по КПД/i);
});


test('scheme stage details retain the physical meaning of source and throttling', async ({page}) => {
  await fixture(page);
  await section(page, 'scheme');
  await page.getByRole('button', {name: 'Приём воды', exact: true}).click();
  await expect(page.getByLabel('Выбранное оборудование')).toContainText('Подача за сутки');
  await page.getByRole('button', {name: 'ЗРА / штуцеры', exact: true}).click();
  await expect(page.getByLabel('Выбранное оборудование')).toContainText('дросселирование');
});
