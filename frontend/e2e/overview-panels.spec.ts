import { test, expect } from '@playwright/test';

for (const width of [1800, 1280]) {
  test(`overview panels keep height and animate the requested proportions at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/?object=kns54an&aggregate=НА-1&mode=field_trip#overview');
    const panels = page.locator('.overview-primary > .page-panel');
    await expect(panels).toHaveCount(2);
    const before = await panels.evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect()));
    expect(before[0].height).toBeCloseTo(before[1].height, 1);
    expect(before[0].width / before[1].width).toBeCloseTo(4 / 5, 2);

    for (const [index, name, share] of [[0, 'Ориентиры УРЭ', .75], [1, 'Диагностика агрегата', .4]] as const) {
      const panel = panels.nth(index);
      const button = page.getByRole('button', { name, exact: true });
      for (const open of [true, false]) {
        await panel.evaluate(node => {
          (window as any).__overviewFrames = [];
          (window as any).__overviewFramesDone = false;
          node.addEventListener('click', () => {
            const start = performance.now();
            const sample = () => {
              const bounds = node.getBoundingClientRect();
              const main = node.querySelector('.overview-metric-main')!.getBoundingClientRect();
              (window as any).__overviewFrames.push({ height: bounds.height, width: main.width });
              if (performance.now() - start < 350) requestAnimationFrame(sample);
              else (window as any).__overviewFramesDone = true;
            };
            requestAnimationFrame(sample);
          }, { once: true });
        });
        await button.click();
        await expect(button).toHaveAttribute('aria-expanded', String(open));
        await page.waitForFunction(() => (window as any).__overviewFramesDone && document.querySelectorAll('.overview-metric-values.is-animating').length === 0);
        const frames = await page.evaluate(() => (window as any).__overviewFrames as { height: number; width: number }[]);
        expect(Math.max(...frames.map(frame => frame.height)) - Math.min(...frames.map(frame => frame.height))).toBeLessThan(1);
        expect(new Set(frames.map(frame => Math.round(frame.width))).size).toBeGreaterThan(2);
        const ratio = await panel.evaluate(node => node.querySelector('.overview-metric-main')!.getBoundingClientRect().width / node.querySelector('.overview-metric-values')!.getBoundingClientRect().width);
        expect(ratio).toBeCloseTo(open ? share : 1, 2);
        expect(await panel.evaluate(node => node.getBoundingClientRect().height)).toBeCloseTo(before[index].height, 1);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      }
    }
  });
}

test('diagnostic values retain explanations and actions after opening, including on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 1800, height: 1000 });
  await page.goto('/?object=kns54an&aggregate=НА-1&mode=field_trip#overview');
  await page.getByRole('button', { name: 'Диагностика агрегата', exact: true }).click();
  const load = page.getByRole('button', { name: 'Пояснение: Коэф. загрузки ЭД', exact: true });
  await load.hover();
  const tooltip = page.locator('[role="tooltip"][data-state="open"]');
  await expect(tooltip).toContainText('K > 1 означает перегрузку.');
  await expect(tooltip).toContainText('Значение сравнивается с 1.');
  await expect(tooltip.locator('p')).toHaveCount(4);
  await page.keyboard.press('Escape');
  await page.getByLabel('Разобрать: Коэф. загрузки ЭД', { exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Действия: Коэф. загрузки ЭД' }).getByRole('link', { name: 'Источники' })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 390, height: 1000 });
  await expect(load).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('passport opens from the whole heading row and supports the keyboard', async ({ page }) => {
  await page.goto('/?object=kns54an&aggregate=НА-1&mode=field_trip#overview');
  const passport = page.locator('.passport-panel');
  const heading = passport.locator('summary');
  const pump = passport.getByRole('heading', { name: 'Насос', exact: true });
  await expect(heading).toHaveText('Паспорт и исходный режим');
  expect(await heading.evaluate(node => node.querySelector('svg')!.getBoundingClientRect().right < node.querySelector('h2')!.getBoundingClientRect().left)).toBe(true);
  await expect(pump).not.toBeVisible();
  const bounds = await heading.boundingBox();
  await heading.click({ position: { x: bounds!.width - 12, y: bounds!.height / 2 } });
  await expect(pump).toBeVisible();
  await expect(passport.getByText('Номинальная подача (Q_ном), м³/ч', { exact: true })).toBeVisible();
  await expect(passport.getByText('Плотность (ρ), кг/м³', { exact: true })).toBeVisible();
  await heading.press('Space');
  await expect(pump).not.toBeVisible();
  await heading.press('Enter');
  await expect(pump).toBeVisible();
});
