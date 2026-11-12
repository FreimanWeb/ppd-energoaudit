import { test, expect } from '@playwright/test';

test('a loss returns from a dated characteristic edit to the same calculation', async ({page, request}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto('/?object=knsopu&mode=field_trip&aggregate=НА-1#machine-losses');
  await page.getByRole('button', {name: /^Потери в передаче/}).click();
  const selected = page.getByLabel('Выбранная составляющая');
  const before = await selected.locator('.machine-loss-selected-value').innerText();
  const calculation = page.url();
  await selected.getByRole('link', {name: 'Проверить характеристики', exact: true}).click();
  const efficiency = page.getByLabel('КПД механической передачи (η_передачи), доля', {exact: true});
  await expect(efficiency).toHaveValue('0.97');
  await page.reload();
  await expect(efficiency).toHaveValue('0.97');
  await expect(page.getByRole('link', {name: 'Вернуться к расчёту', exact: true})).toBeVisible();
  await efficiency.fill('0.96');
  const editing = page.url();
  page.once('dialog', dialog => dialog.dismiss());
  await page.getByRole('link', {name: 'Вернуться к расчёту', exact: true}).click();
  await expect(page).toHaveURL(editing);
  await expect(efficiency).toHaveValue('0.96');
  await page.getByLabel('Действует с *', {exact: true}).fill('2026-01-01T00:00');
  await page.getByLabel('Источник данных *', {exact: true}).fill('Изолированная проверка возврата');
  await page.getByLabel('Автор записи *', {exact: true}).fill('Browser test');
  await page.getByRole('button', {name: 'Сохранить', exact: true}).click();
  await page.getByRole('button', {name: 'Подтвердить и сохранить', exact: true}).click();
  await expect(page.getByRole('status').filter({hasText: 'Изменение сохранено'})).toBeVisible();
  try {
    await page.getByRole('link', {name: 'Вернуться к расчёту', exact: true}).click();
    await expect(page).toHaveURL(calculation);
    await expect(selected).toBeFocused();
    await expect(selected.locator('.machine-loss-selected-value')).toContainText('кВт');
    await expect(selected.locator('.machine-loss-selected-value')).not.toHaveText(before);
    await expect(page.getByRole('button', {name: /^Потери в передаче/})).toHaveAttribute('aria-pressed', 'true');
    await page.goBack();
    await expect(page.getByRole('heading', {name: 'Характеристики оборудования', exact: true})).toBeVisible();
    await page.goForward();
    await expect(page).toHaveURL(calculation);
    await expect(selected).toBeVisible();
    for (const width of [390, 1440]) {
      await page.setViewportSize({width, height: 900});
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
    }
  } finally {
    const base = '/api/objects/knsopu/aggregates/' + encodeURIComponent('НА-1') + '/equipment-journal';
    const journal = await (await request.get(base)).json();
    const entry = journal.items.find((item: {source: string; superseded_by: number | null}) => item.source === 'Изолированная проверка возврата' && item.superseded_by == null);
    const response = await request.post(base, {data: {
      component: 'transmission', effective_at: '2026-01-01T00:00:00', expected_revision: journal.revision,
      changes: {'transmission.efficiency': 0.97}, reason: 'correction', evidence: 'estimate',
      source: 'Восстановление изолированной проверки', author: 'Browser test', comment: '', supersedes_id: entry.id,
    }});
    expect(response.ok(), await response.text()).toBeTruthy();
  }
});

test('returning from the detailed calculation restores the selected loss and scroll position', async ({page}) => {
  await page.setViewportSize({width: 390, height: 780});
  await page.goto('/?object=knsopu&mode=field_trip&aggregate=НА-1#machine-losses');
  await page.getByRole('button', {name: /^Потери в насосе/}).click();
  const link = page.getByLabel('Выбранная составляющая').getByRole('link', {name: 'Расчёт и источники', exact: true});
  await link.scrollIntoViewIfNeeded();
  const position = await page.evaluate(() => scrollY);
  await link.click();
  await page.getByRole('link', {name: 'К карте потерь', exact: true}).click();
  await expect(page.getByRole('button', {name: /^Потери в насосе/})).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByLabel('Выбранная составляющая')).toBeFocused();
  await expect.poll(async () => Math.abs(await page.evaluate(() => scrollY) - position)).toBeLessThan(3);
});
