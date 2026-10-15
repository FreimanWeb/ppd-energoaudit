import { test, expect } from '@playwright/test';

test('pointer focus has no chart frame, while Tab outlines chart elements in black', async ({page})=>{
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29#losses');
  const plot=page.locator(".page-panel:not(:has(.network-losses))").getByRole('group',{name:'Декомпозиция мощности',exact:true});
  const svg=plot.locator('svg.visx-chart');
  await expect(svg).toBeVisible();
  await svg.click({position:{x:100,y:10}});
  await svg.evaluate(element=>(element as SVGSVGElement).focus());
  expect(await svg.evaluate(element=>getComputedStyle(element).outlineWidth)).toBe('0px');
  await page.locator('.page-panel:not(:has(.network-losses))').getByRole('button',{name:'Структура, %',exact:true}).focus();
  await page.keyboard.press('Tab');
  const bar=plot.locator('.visx-bar').first();
  await expect(bar).toBeFocused();
  await expect.poll(()=>bar.evaluate(element=>getComputedStyle(element).stroke)).toBe('rgb(0, 0, 0)');
  await svg.click({position:{x:100,y:10}});
  await svg.evaluate(element=>(element as SVGSVGElement).focus());
  expect(await svg.evaluate(element=>getComputedStyle(element).outlineWidth)).toBe('0px');

  await page.locator('.page-panel:not(:has(.network-losses))').getByRole('button',{name:'Поток мощности',exact:true}).click();
  const flow=page.locator(".page-panel:not(:has(.network-losses))").getByRole('group',{name:'Поток мощности',exact:true});
  await expect(flow.locator('svg.visx-chart')).toBeVisible();
  await page.locator('.page-panel:not(:has(.network-losses))').getByRole('button',{name:'Структура, %',exact:true}).focus();
  await page.keyboard.press('Tab');
  const link=flow.locator('.flow-link').first();
  await expect(link).toBeFocused();
  expect(await link.evaluate(element=>getComputedStyle(element).outlineColor)).toBe('rgb(0, 0, 0)');
  const position=await link.evaluate(element=>{
    const path=element as SVGPathElement, point=path.getPointAtLength(path.getTotalLength()/2), matrix=path.getScreenCTM()!;
    return {x:point.x*matrix.a+point.y*matrix.c+matrix.e,y:point.x*matrix.b+point.y*matrix.d+matrix.f};
  });
  await page.mouse.click(position.x,position.y);
  expect(await link.evaluate(element=>getComputedStyle(element).outlineWidth)).toBe('0px');
});
