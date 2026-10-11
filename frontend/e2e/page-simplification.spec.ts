import { test, expect } from '@playwright/test';

const context = '/?object=kns54an&aggregate=НА-1&day=2026-09-29';

test('overview keeps fact and calculation primary and preserves secondary references', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(context + '#overview');
  const ure = page.locator('.page-panel').filter({ has: page.getByRole('heading', { name: 'Удельный расход энергии', exact: true }) });
  await expect(ure.getByText('Факт', { exact: true })).toBeVisible();
  await expect(ure.getByText('Расчётный', { exact: true })).toBeVisible();
  await expect(ure.getByText('Цель ППД-2035', { exact: true })).not.toBeVisible();
  await page.screenshot({ path: '/tmp/ppd-overview-table.png', fullPage: true });
  await ure.getByText('Ориентиры УРЭ', { exact: true }).click();
  await expect(ure.getByText('Цель ППД-2035', { exact: true })).toBeVisible();
  await expect(ure.getByText('Оптимальный', { exact: true })).toBeVisible();
  const diagnostic = page.getByText('Диагностика агрегата', { exact: true });
  await diagnostic.click();
  await expect(page.getByText('КПД насоса расчётный', { exact: true })).toBeVisible();
});

test('formula groups retain all entries including unknown methodology numbers', async ({ page }) => {
  await page.route('**/snapshot-audit', async route => {
    const response = await route.fetch();
    const audit = await response.json();
    audit.audit.trace['999'] = { name: 'Дополнительный расчёт', formula: 'x = 0', subst: '0', value: 0 };
    await route.fulfill({ response, json: audit });
  });
  await page.goto(context + '#formulas');
  for (const name of ['Напор', 'Мощность', 'КПД и загрузка', 'Удельный расход энергии', 'Годовые потери', 'Другие расчёты'])
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  await expect(page.getByText('(999) Дополнительный расчёт', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Раскрыть все', exact: true }).click();
  await expect(page.getByText('x = 0', { exact: true })).toBeVisible();
  await expect(page.locator('.formula-card details:not([open])')).toHaveCount(0);
});

test('readiness prioritizes missing basic inputs without declaring optional curves required', async ({ page }) => {
  await page.route('**/onboarding?*', async route => {
    const response = await route.fetch();
    const data = await response.json();
    for (const check of data.checks) if (check.field === 'Паспорт ЭД: η_ном' || check.field === 'Кривая Q-H') {
      check.present = false;
      check.value = null;
    }
    const inlet = data.checks.find((check: {field: string}) => check.field === "Телеметрия: p_вх");
    inlet.value = 0;
    inlet.present = false;
    await route.fulfill({ response, json: data });
  });
  await page.goto(context + '#onboarding');
  const missing = page.getByRole('region', { name: 'Недостающие базовые данные', exact: true });
  await expect(missing).toContainText('Паспорт ЭД: η_ном');
  await expect(missing).not.toContainText('Кривая Q-H');
  await expect(missing).not.toContainText('Телеметрия: p_вх');
  await expect(page.getByRole('row').filter({ hasText: 'Телеметрия: p_вх' })).toContainText('Есть');
  await expect(page.getByText(/Часть полей опциональна/)).toBeVisible();
  await expect(page.getByText('Шаблон паспорта объекта', { exact: true })).toBeVisible();
});
