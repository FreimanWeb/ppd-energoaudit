import { test, expect } from '@playwright/test';

test('moving the shared cursor reuses chart models and numeric formatters', async ({ page }) => {
  await page.addInitScript(() => {
    (window as any).__numberFormatBuilds = 0;
    Intl.NumberFormat = new Proxy(Intl.NumberFormat, {
      construct(target, args) {
        (window as any).__numberFormatBuilds++;
        return Reflect.construct(target, args);
      },
    });
  });
  await page.route('**/src/charts/chartModel.mjs*', async route => {
    const response = await route.fetch();
    const source = (await response.text()).replace('export function buildChartModel(', 'function originalBuildChartModel(');
    await route.fulfill({ response, body: source + '\nexport function buildChartModel(...args) { window.__chartModelBuilds = (window.__chartModelBuilds || 0) + 1; return originalBuildChartModel(...args); }' });
  });
  const times = Array.from({ length: 24 }, (_, i) => `2026-09-29T00:${String(i).padStart(2, '0')}:00`);
  await page.route('**/api/objects/kns54an/telemetry?*', route => route.fulfill({ json: {
    records: Array.from({ length: 200 }, (_, i) => ({ timestamp: times[i % times.length], metric: 'P_эл', value: 600 + i, unit: 'кВт' })),
    series: [
      { metric: 'P_вх', unit: 'МПа', points: times.map((timestamp, i) => ({ timestamp, value: 2 + i / 10 })) },
      { metric: 'P_эл', unit: 'кВт', points: times.map((timestamp, i) => ({ timestamp, value: 600 + i })) },
    ],
  } }));
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29&timestamp=2026-09-29T00%3A00%3A00#telemetry');
  await expect(page.getByLabel('Момент измерения', { exact: true })).toHaveValue(times[0]);
  const chart = page.getByRole('group', { name: 'Давления', exact: true }).locator('svg.visx-chart');
  await expect(chart).toBeVisible();
  await expect(page.locator('table tbody tr')).toHaveCount(200);
  const builds = await chart.evaluate(async node => {
    await new Promise(resolve => requestAnimationFrame(resolve));
    (window as any).__chartModelBuilds = 0;
    (window as any).__numberFormatBuilds = 0;
    const bounds = node.getBoundingClientRect();
    for (let i = 0; i < 12; i++) {
      node.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, pointerType: 'mouse', clientX: bounds.left + 80 + i * (bounds.width - 120) / 12, clientY: bounds.top + 60 }));
      await new Promise(resolve => requestAnimationFrame(resolve));
    }
    return { models: (window as any).__chartModelBuilds, formats: (window as any).__numberFormatBuilds };
  });
  expect(builds.models).toBe(0);
  expect(builds.formats).toBe(0);
  await expect(page.locator('main .visx-crosshair')).toHaveCount(2);
});
