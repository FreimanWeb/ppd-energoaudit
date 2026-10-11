import { test, expect } from '@playwright/test';

test('overview groups efficiency and opens references horizontally without nested card frames', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29#overview');
  await expect(page.getByRole('heading', { name: /^Топ мероприятий/ })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Карта потерь мощности →', exact: true })).toHaveCount(0);
  const top = page.locator('.page-panel').filter({ has: page.getByRole('heading', { name: /^Топ мероприятий/ }) });
  const all = top.getByRole('link', { name: 'Все →', exact: true });
  await expect(all).toHaveAttribute('href', '#measures');
  const heading = (await top.getByRole('heading', { name: /^Топ мероприятий/ }).boundingBox())!;
  const link = (await all.boundingBox())!;
  expect(link.x).toBeGreaterThan(heading.x + heading.width);
  expect(Math.abs(link.y + link.height / 2 - heading.y - heading.height / 2)).toBeLessThan(2);
  const ure = page.locator('.page-panel').filter({ has: page.getByRole('heading', { name: 'Удельный расход энергии', exact: true }) });
  const toggle = ure.getByRole('button', { name: 'Ориентиры УРЭ', exact: true });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  const reference = ure.getByText('Цель ППД-2035', { exact: true });
  await expect(reference).toBeVisible();
  await expect.poll(async () => {
    const a = (await ure.getByText('Факт', { exact: true }).boundingBox())!;
    const b = (await reference.boundingBox())!;
    return b.x > a.x && Math.abs(a.y - b.y) < 2;
  }).toBe(true);
  const efficiency = page.locator('.page-panel').filter({ has: page.getByRole('heading', { name: 'КПД', exact: true }) });
  await expect(efficiency.locator('.metric-segment-divider')).toHaveCount(1);
  await efficiency.getByText('Диагностика агрегата', { exact: true }).click();
  for (const name of ['Коэф. загрузки ЭД', 'КПД ЭД расчётный', 'КПД насоса расчётный'])
    await expect(efficiency.getByText(name, { exact: true })).toBeVisible();
  const working = page.getByRole('group', { name: 'Режим выбранного агрегата', exact: true });
  await expect(working.getByText('КПД насоса расчётный', { exact: true })).toHaveCount(0);
  for (const panel of [ure, efficiency])
    for (const card of await panel.locator('.metric-card').all()) {
      const style = await card.evaluate(el => ({ shadow: getComputedStyle(el).boxShadow, border: getComputedStyle(el).borderTopWidth }));
      expect(style.shadow).toBe('none');
      expect(style.border).toBe('0px');
    }
  await page.screenshot({ path: "/tmp/ppd-overview-polish.png", fullPage: true });
  await toggle.click();
  await expect(reference).not.toBeVisible();
});
