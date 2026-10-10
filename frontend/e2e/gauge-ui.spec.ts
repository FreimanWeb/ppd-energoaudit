import { test, expect } from '@playwright/test';

test('efficiency gauge sits below the two KPI cards without a duplicate caption', async ({ page }) => {
  await page.goto('/?object=kns54an&aggregate=' + encodeURIComponent('НА-1') + '&day=2026-09-29#overview');

  const panel = page.locator('.page-panel').filter({
    has: page.getByRole('heading', { name: 'КПД агрегата и КПД номинальный', exact: true }),
  });
  await expect(panel.locator('.metric-card')).toHaveCount(2);
  const disclosure = panel.locator('.metric-efficiency-disclosure');
  const verticalOrder = await panel.evaluate((element) => {
    const cards = [...element.querySelectorAll('.metric-card')];
    const gauge = element.querySelector('.metric-efficiency-disclosure');
    return {
      cardBottom: Math.max(...cards.map((card) => card.getBoundingClientRect().bottom)),
      gaugeTop: gauge?.getBoundingClientRect().top ?? 0,
      cardLeft: Math.min(...cards.map((card) => card.getBoundingClientRect().left)),
      cardRight: Math.max(...cards.map((card) => card.getBoundingClientRect().right)),
      gaugeLeft: gauge?.getBoundingClientRect().left ?? 0,
      gaugeRight: gauge?.getBoundingClientRect().right ?? 0,
    };
  });
  expect(verticalOrder.gaugeTop).toBeGreaterThanOrEqual(verticalOrder.cardBottom);
  expect(Math.abs(verticalOrder.gaugeLeft - verticalOrder.cardLeft)).toBeLessThan(1);
  expect(Math.abs(verticalOrder.gaugeRight - verticalOrder.cardRight)).toBeLessThan(1);

  await disclosure.locator('summary').click();
  const gauge = panel.locator('.gauge-chart');
  await expect(gauge).toBeVisible();
  await expect(gauge.locator('.gauge-caption')).toHaveCount(0);
  await expect(gauge).toHaveAttribute('role', 'img');
  await expect(gauge).toHaveAttribute('aria-label', /Фактический КПД.*номинальный/);
  const bands = gauge.locator('.gauge-band');
  await expect(bands).toHaveCount(3);
  expect(await bands.evaluateAll((paths) => new Set(paths.map((path) => path.getAttribute('fill'))).size)).toBe(3);
});
