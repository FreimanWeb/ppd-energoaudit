import { test, expect } from '@playwright/test';

test('component catalogue exposes real numeric, loading and calendar states', async ({ page }, testInfo) => {
  await page.goto('/design-system.html');
  await expect(page.getByRole('heading', { name: 'Дизайн-система', exact: true })).toBeVisible();
  const info = page.locator('.tooltip-trigger').first();
  expect((await info.boundingBox())!.width).toBe(20);
  expect((await info.locator('svg').boundingBox())!.width).toBe(14);
  const loading = page.getByRole('button', { name: 'Загружаем', exact: true });
  await expect(loading).toHaveAttribute('aria-busy', 'true');
  await expect(loading).toBeDisabled();
  const numeric = page.locator('td.numeric-cell').first();
  expect(await numeric.evaluate(element => getComputedStyle(element).textAlign)).toBe('end');
  expect(await numeric.evaluate(element => getComputedStyle(element).fontVariantNumeric)).toContain('tabular-nums');
  const contrasts = await page.evaluate(() => {
    const luminance = (color: string) => {
      const rgb = color.match(/[\d.]+/g)!.slice(0, 3).map(Number).map(channel => {
        const value = channel / 255;
        return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4;
      });
      return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
    };
    return [...document.querySelectorAll('.metric-unit, .metric-segment-label, .metric-card strong, .ds-button:not(:disabled), .catalogue-nav a')].map(element => {
      const style = getComputedStyle(element);
      let ancestor: Element | null = element;
      let background = 'rgb(255, 255, 255)';
      while (ancestor) {
        const candidate = getComputedStyle(ancestor).backgroundColor;
        if (candidate !== 'rgba(0, 0, 0, 0)' && candidate !== 'transparent') { background = candidate; break; }
        ancestor = ancestor.parentElement;
      }
      const foreground = luminance(style.color), backdrop = luminance(background);
      return { label: element.textContent, ratio: (Math.max(foreground, backdrop) + .05) / (Math.min(foreground, backdrop) + .05), minimum: parseFloat(style.fontSize) >= 24 ? 3 : 4.5 };
    });
  });
  for (const result of contrasts) expect(result.ratio, result.label ?? 'text contrast').toBeGreaterThanOrEqual(result.minimum);
  const dateTrigger = page.getByRole('button', { name: 'Дата', exact: true });
  const dateBox = (await dateTrigger.boundingBox())!, iconBox = (await dateTrigger.locator('svg').boundingBox())!;
  expect(Math.abs((iconBox.y + iconBox.height / 2) - (dateBox.y + dateBox.height / 2))).toBeLessThan(1);
  expect(dateBox.x + dateBox.width - iconBox.x - iconBox.width).toBeGreaterThanOrEqual(14);
  await dateTrigger.click();
  await expect(page.getByRole('dialog', { name: 'Выбор даты' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Дата', exact: true })).toBeFocused();
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await expect(page.locator('.table-scroll-hint').first()).toBeVisible();
  await page.getByRole('region', { name: 'Таблица с горизонтальной прокруткой' }).first().focus();
  await expect(page.getByRole('region', { name: 'Таблица с горизонтальной прокруткой' }).first()).toBeFocused();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  expect(await page.locator('.button-spinner').evaluate(element => getComputedStyle(element).animationName)).toBe('none');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: testInfo.outputPath('catalogue-desktop.png'), fullPage: true });
});

test('all application sections keep page-level reflow at desktop and narrow widths', async ({ page }, testInfo) => {
  test.setTimeout(120000);
  const sections = ['overview', 'snapshot', 'telemetry', 'scheme', 'forecast', 'crm', 'crm-wells', 'losses', 'working-point', 'measures', 'sources', 'formulas', 'onboarding'];
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/?object=kns54an&aggregate=' + encodeURIComponent('НА-1') + '&day=2026-09-29#overview');
  await expect(page.getByRole('heading', { name: /^Годовая оценка/ })).toBeVisible();
  for (const section of sections) {
    await page.evaluate(hash => { location.hash = hash; }, section);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.locator('main').getByText(/^(Загружаем данные…|Загружаем график…)$/)).toHaveCount(0, { timeout: 20000 });
    await page.waitForLoadState('networkidle');
    if (section === 'formulas') await page.getByRole('button', { name: 'Раскрыть все', exact: true }).click();
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${section} at ${width}px`).toBe(true);
      if (section === 'formulas' && width === 320) await expect(page.getByRole('region', { name: 'Формула с горизонтальной прокруткой' }).first()).toBeVisible();
      if (width !== 320) await page.screenshot({ path: testInfo.outputPath(`${section}-${width}.png`), fullPage: true });
    }
  }
  expect(errors).toEqual([]);
});
