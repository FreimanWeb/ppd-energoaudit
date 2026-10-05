import { test, expect } from '@playwright/test';

test('CRM graph accepts a real click on a visible well', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Объект', { exact: true }).selectOption('kns54an');
  await page.getByLabel('Агрегат', { exact: true }).selectOption('НА-1');
  await page.getByLabel('Дата', { exact: true }).selectOption('2026-09-29');
  await expect(page.getByText('600', { exact: true }).first()).toBeVisible();
  await page.locator('nav a[href="#crm-wells"]').click();
  const graph = page.locator('.js-plotly-plot').last();
  const node = graph.locator('.scatterlayer .trace:last-child .point').first();
  await expect(node).toBeVisible();
  await node.scrollIntoViewIfNeeded();
  const box = await node.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await expect(page.getByLabel('Скважина графа')).not.toHaveValue('');
});

test('charts fit their container after mobile resize', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Объект', { exact: true }).selectOption('kns54an');
  await page.getByLabel('Агрегат', { exact: true }).selectOption('НА-1');
  await page.getByLabel('Дата', { exact: true }).selectOption('2026-09-29');
  await expect(page.getByText('600', { exact: true }).first()).toBeVisible();
  await page.locator('nav a[href="#losses"]').click();
  const plots = page.locator('.js-plotly-plot');
  await expect(plots.first()).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(async () => plots.evaluateAll(elements => elements.every(el => {
    const plot = el as HTMLElement & { _fullLayout?: { width: number } };
    return !!plot._fullLayout && plot._fullLayout.width <= plot.clientWidth + 1;
  }))).toBe(true);
  await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const sankey = page.getByRole('group', { name: 'Поток мощности' });
  await expect.poll(async () => sankey.evaluate(el => {
    const plot = el.getBoundingClientRect();
    const nodes = [...el.querySelectorAll('.sankey-node .node-rect')];
    return nodes.length >= 2 && nodes.every(node => {
      const box = node.getBoundingClientRect();
      return box.left >= plot.left && box.right <= plot.right;
    });
  })).toBe(true);
  const anchors = await sankey.locator('.sankey-node .node-label').evaluateAll(labels =>
    labels.map(label => ({
      intended: label.getAttribute('text-anchor'),
      actual: getComputedStyle(label).textAnchor,
    })),
  );
  expect(anchors.length).toBeGreaterThanOrEqual(2);
  for (const anchor of anchors) expect(anchor.actual).toBe(anchor.intended);
  await page.screenshot({path:'/tmp/ppd-mobile-losses-after-resize.png',fullPage:true});
});
