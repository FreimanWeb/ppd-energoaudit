import {test, expect} from '@playwright/test';
import {selectDate} from './helpers';

test('cards and KPIs render while history waits, and period changes only reload graphs', async ({page}) => {
  let release!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  const summaries: string[] = [];
  page.on('request', request => {
    if (request.url().includes('/monitoring/objects')) summaries.push(request.url());
  });
  await page.route('**/api/monitoring/history?**', async route => {
    await waiting;
    await route.continue();
  });
  try {
    await page.goto('/');
    const cards = page.locator('.portfolio-card');
    await expect(cards).toHaveCount(4);
    await expect(cards.first().locator('.portfolio-reading strong').first()).not.toHaveText('— кВт·ч/м³');
    await expect(page.getByLabel('Загрузка истории УРЭ')).toHaveCount(4);
    const height = (await cards.first().boundingBox())!.height;
    release();
    await expect(page.getByLabel('Загрузка истории УРЭ')).toHaveCount(0);
    await expect(page.locator('.portfolio-sparkline').first()).toBeVisible();
    expect(Math.abs((await cards.first().boundingBox())!.height - height)).toBeLessThan(2);
    const kpis = await page.locator('.portfolio-reading').allTextContents();
    const summaryCount = summaries.length;
    const response = page.waitForResponse(r => r.url().includes('/monitoring/history?history_days=7'));
    await page.getByLabel('Период графиков').selectOption('7');
    await response;
    await expect(page.getByLabel('Загрузка истории УРЭ')).toHaveCount(0);
    expect(await page.locator('.portfolio-reading').allTextContents()).toEqual(kpis);
    const dated = page.waitForResponse(r => r.url().includes('/monitoring/history?') && r.url().includes('history_end=2026-09-29'));
    await selectDate(page, '2026-09-29', 'Дата окончания графиков');
    await dated;
    await expect(page.getByLabel('Загрузка истории УРЭ')).toHaveCount(0);
    expect(await page.locator('.portfolio-reading').allTextContents()).toEqual(kpis);
    expect(summaries).toHaveLength(summaryCount);
    expect(summaries[0]).toContain('include_history=false');
  } finally {
    release();
  }
});

test('history errors stay inside graphs and keep the cards usable', async ({page}) => {
  await page.route('**/api/monitoring/history?**', route => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({detail: 'История недоступна.'}),
  }));
  await page.goto('/');
  await expect(page.locator('.portfolio-card')).toHaveCount(4);
  await expect(page.locator('.portfolio-card [role=alert]')).toHaveCount(4);
  await page.getByRole('button', {name: 'Открыть историю: КНС-54', exact: true}).click();
  await expect.poll(() => new URL(page.url()).hash).toBe('#timeline');
});
