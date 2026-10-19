import { goToSection } from "./helpers";
import { test, expect, type Page } from '@playwright/test';
import { selectDate } from './helpers';

async function fixture(page: Page) {
  await page.goto('/#machine-block');
  await page.getByLabel('Объект', { exact: true }).selectOption('kns54an');
  await page.getByLabel('Агрегат', { exact: true }).selectOption('НА-1');
  await selectDate(page, '2026-09-29');
  await expect(page.getByRole("heading",{name:"Удельный расход энергии",exact:true})).toBeVisible();
}

test('CRM graph accepts a real well click and keyboard activation', async ({ page }) => {
  await fixture(page);
  await goToSection(page, "crm-wells");
  await page.getByRole('button', { name: 'Связи', exact: true }).click();
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

test('loss charts scroll locally and retain full labels on mobile', async ({ page }) => {
  await fixture(page);
  await goToSection(page, "machine-block");
  await page.setViewportSize({ width: 390, height: 844 });
  const plot=page.locator('.page-panel:not(:has(.network-losses))').getByRole('group',{name:'Декомпозиция мощности',exact:true});
  await expect(plot.locator('svg.visx-chart')).toBeVisible();
  await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const labels=await plot.locator('.visx-axis-x text').allTextContents();
  expect(labels.length).toBeGreaterThanOrEqual(2);
  expect(labels.every(text=>text && !text.includes('…'))).toBe(true);
  await expect(page.getByRole('button',{name:'Поток мощности',exact:true})).toHaveCount(0);
});
