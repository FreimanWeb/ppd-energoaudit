import { test, expect, type Page } from '@playwright/test';
import { selectDate } from './helpers';

async function fixture(page: Page) {
  await page.goto('/');
  await page.getByLabel('Объект', { exact: true }).selectOption('kns54an');
  await page.getByLabel('Агрегат', { exact: true }).selectOption('НА-1');
  await selectDate(page, '2026-09-29');
  await expect(page.getByText('600', { exact: true }).first()).toBeVisible();
}

test('CRM graph accepts a real well click and keyboard activation', async ({ page }) => {
  await fixture(page);
  await page.locator('nav a[href="#crm-wells"]').click();
  const graph = page.getByRole('group', { name: 'Граф взаимовлияния', exact: true });
  const nodes = graph.getByRole('button', { name: /^Скважина / });
  const node = nodes.first();
  await expect(node).toBeVisible();
  const well = (await node.getAttribute('aria-label'))!.replace('Скважина ', '');
  await node.click();
  await expect(page.getByLabel('Скважина графа')).toHaveValue(well);
  await expect(node).toHaveAttribute('aria-pressed', 'true');
  await page.getByLabel('Скважина графа').selectOption('');
  await node.focus();
  await node.press('Enter');
  await expect(page.getByLabel('Скважина графа')).toHaveValue(well);
  await page.getByLabel('Скважина графа').selectOption('');
  await node.focus();
  await node.press('Space');
  await expect(page.getByLabel('Скважина графа')).toHaveValue(well);
});

test('charts and full flow labels fit their container after mobile resize', async ({ page }) => {
  await fixture(page);
  await page.locator('nav a[href="#losses"]').click();
  await page.getByRole('button', { name: 'Поток мощности', exact: true }).click();
  const plots = page.locator('svg.visx-chart');
  await expect(plots.first()).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(async () => plots.evaluateAll(elements => elements.length > 0 && elements.every(el => {
    const chart = el.getBoundingClientRect();
    const container = el.closest('.plot-wrap')!.getBoundingClientRect();
    return chart.width > 0 && chart.width <= container.width + 1;
  }))).toBe(true);
  await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const sankey = page.getByRole('group', { name: 'Поток мощности', exact: true });
  await expect.poll(async () => sankey.evaluate(el => {
    const plot = el.getBoundingClientRect();
    const nodes = [...el.querySelectorAll('.flow-node rect')];
    return nodes.length >= 2 && nodes.every(node => {
      const box = node.getBoundingClientRect();
      return box.left >= plot.left && box.right <= plot.right;
    });
  })).toBe(true);
  const labelBounds = await sankey.locator('.flow-node-label').evaluateAll(labels =>
    labels.map(label => ({ width: label.getBoundingClientRect().width, text: label.textContent })),
  );
  expect(labelBounds.length).toBeGreaterThanOrEqual(2);
  expect(labelBounds.every(label => label.width > 0 && label.text)).toBe(true);
  await expect(sankey.getByLabel('Состав потока мощности')).toContainText('Подведённая мощность');
  await expect(sankey.getByLabel('Состав потока мощности')).toContainText('Полезная мощность');
});
