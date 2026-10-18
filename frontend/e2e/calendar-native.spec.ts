import { test, expect } from '@playwright/test';

const context = '/?object=kns54an&aggregate=НА-1&day=2026-09-29&timestamp=2026-09-29T12%3A00%3A00&mode=analysis#machine-block';

test('one date trigger opens colored calendar and keeps selection while browsing months', async ({ page }) => {
  await page.goto(context);
  const date = page.getByRole('button', { name: 'Дата', exact: true });
  await expect(date).toHaveAttribute('data-date', '2026-09-29');
  await expect(page.locator('select[aria-label="Дата"]')).toHaveCount(0);
  await date.click();
  const dialog = page.getByRole('dialog', { name: 'Выбор даты' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: '2026-09-29: Пригодные сутки', exact: true })).toHaveClass(/ready/);
  await expect(dialog.getByRole('button', { name: '2026-09-30: Непригодные данные', exact: true })).toHaveClass(/unfit/);
  await page.getByLabel('Месяц календаря').fill('2026-07');
  await expect(date).toHaveAttribute('data-date', '2026-09-29');
  await expect(page.getByLabel('Момент измерения')).toHaveValue('2026-09-29T12:00:00');
  await dialog.getByRole('button', { name: '2026-07-01: Пригодные сутки', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(date).toHaveAttribute('data-date', '2026-07-01');
  await expect(date).toBeFocused();
});

test('calendar closes on Escape and outside click, retaining unavailable chosen date', async ({ page }) => {
  await page.goto(context.replace('2026-09-29', '2026-06-01'));
  const date = page.getByRole('button', { name: 'Дата', exact: true });
  await expect(date).toHaveAttribute('data-date', '2026-06-01');
  await date.click();
  await expect(page.getByLabel('Месяц календаря')).toHaveValue('2026-07');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog', { name: 'Выбор даты' })).toHaveCount(0);
  await expect(date).toBeFocused();
  await expect(date).toHaveAttribute('data-date', '2026-06-01');
  await date.click();
  await page.locator('.page-heading').click();
  await expect(page.getByRole('dialog', { name: 'Выбор даты' })).toHaveCount(0);
  await expect(date).toHaveAttribute('data-date', '2026-06-01');
});

test('filters precede object, viewer has one calendar, and mobile dialog fits viewport', async ({ page }) => {
  await page.goto(context);
  expect(await page.locator('.selector-filters').evaluate(el => Boolean(el.compareDocumentPosition(document.querySelector('select[aria-label="Объект"]')!) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true);
  await page.getByLabel('Режим', { exact: true }).selectOption('telemetry_view');
  const date = page.getByRole('button', { name: 'Дата', exact: true });
  await expect(date).toHaveCount(1);
  await expect(page.getByLabel('Момент измерения')).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Открыть боковую панель' }).click();
  await date.click();
  const dialog = page.getByRole('dialog', { name: 'Выбор даты' });
  const box = await dialog.boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  expect(box!.y + box!.height).toBeLessThanOrEqual(844);
  await page.keyboard.press('Escape');
  await expect(date).toBeFocused();
  await expect(page.getByRole('button', { name: 'Закрыть боковую панель' })).toBeVisible();
});

test('missing telemetry disables date picker and field trip hides it', async ({ page }) => {
  await page.goto('/?object=kns97pren&aggregate=НА-2%20ПР&mode=analysis#machine-block');
  await expect(page.getByRole('button', { name: 'Дата', exact: true })).toBeDisabled();
  await expect(page.getByText('Энергоаудит системы ППД', { exact: true })).toHaveCount(0);
  await page.getByLabel('Режим', { exact: true }).selectOption('field_trip');
  await expect(page.getByRole('button', { name: 'Дата', exact: true })).toHaveCount(0);
});
