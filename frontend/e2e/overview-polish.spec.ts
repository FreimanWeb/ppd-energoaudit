import { goToSection } from "./helpers";
import { test, expect } from '@playwright/test';

test('overview groups efficiency and keeps references visible without nested card frames', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29#machine-block');
  await expect(page.getByRole('link', { name: 'Карта потерь мощности →', exact: true })).toHaveCount(0);
  await goToSection(page,'machine-losses');
  const top = page.getByRole('region', {name: 'Мероприятия участка'});
  const all = top.getByRole('link', { name: 'Перейти к мероприятиям', exact: true });
  await expect(all).toHaveAttribute('href', /stage=hall.*#measures$/);
  const heading = (await top.getByRole('heading', { name: 'Мероприятия участка', exact: true }).boundingBox())!;
  const link = (await all.boundingBox())!;
  expect(link.x).toBeGreaterThan(heading.x + heading.width);
  expect(Math.abs(link.y + link.height / 2 - heading.y - heading.height / 2)).toBeLessThan(2);
  await goToSection(page,'machine-block');
  const ure = page.locator('.page-panel').filter({ has: page.getByRole('heading', { name: 'Удельный расход энергии', exact: true }) });
  await expect(ure.getByRole('button',{name:'Ориентиры УРЭ',exact:true})).toHaveCount(0);
  const reference=ure.getByText('Цель ППД-2035',{exact:true});
  await expect(reference).toBeVisible();
  const fact=(await ure.getByText('Факт',{exact:true}).boundingBox())!;
  expect((await reference.boundingBox())!.y).toBeGreaterThan(fact.y);
  await expect(page.getByRole('heading',{name:'КПД',exact:true})).toBeVisible();
  await goToSection(page, "machine-block");
  const efficiency = page.locator('.page-panel').filter({ has: page.getByRole('heading', { name: 'КПД', exact: true }) });
  await expect(efficiency.locator('.metric-segment-divider')).not.toBeVisible();
  await expect(efficiency.locator('.machine-efficiency > .metric-group')).toHaveCSS('border-top-width','1px');
  for (const name of ['Коэф. загрузки ЭД', 'КПД ЭД расчётный', 'КПД насоса расчётный'])
    await expect(efficiency.getByText(name, { exact: true })).toBeVisible();
  for (const panel of [efficiency])
    for (const card of await panel.locator('.metric-card').all()) {
      const style = await card.evaluate(el => ({ shadow: getComputedStyle(el).boxShadow, border: getComputedStyle(el).borderTopWidth }));
      expect(style.shadow).toBe('none');
      expect(style.border).toBe('0px');
    }
  await page.screenshot({ path: "/tmp/ppd-overview-polish.png", fullPage: true });
});
