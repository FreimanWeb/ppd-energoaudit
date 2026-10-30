import { test, expect } from '@playwright/test';

test('pointer focus has no chart frame, while Tab outlines chart elements in black', async ({page})=>{
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29#machine-losses');
  const plot=page.locator(".page-panel").filter({has:page.getByRole("heading",{name:/^Цифровая карта потерь мощности/})}).getByRole('group',{name:'Декомпозиция мощности',exact:true});
  const svg=plot.locator('svg.visx-chart');
  await expect(svg).toBeVisible();
  await svg.click({position:{x:100,y:10}});
  await svg.evaluate(element=>(element as SVGSVGElement).focus());
  expect(await svg.evaluate(element=>getComputedStyle(element).outlineWidth)).toBe('0px');
  await page.locator(".page-panel").filter({has:page.getByRole("heading",{name:/^Цифровая карта потерь мощности/})}).getByRole('button',{name:'Структура, %',exact:true}).focus();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button',{name:'Детализация потерь НА',exact:true})).toBeFocused();
  await page.keyboard.press('Tab');
  const bar=plot.locator('.visx-bar').first();
  await expect(bar).toBeFocused();
  await expect.poll(()=>bar.evaluate(element=>getComputedStyle(element).stroke)).toBe('rgb(0, 0, 0)');
  await svg.click({position:{x:100,y:10}});
  await svg.evaluate(element=>(element as SVGSVGElement).focus());
  expect(await svg.evaluate(element=>getComputedStyle(element).outlineWidth)).toBe('0px');

  await expect(page.getByRole('button',{name:'Поток мощности',exact:true})).toHaveCount(0);
});
