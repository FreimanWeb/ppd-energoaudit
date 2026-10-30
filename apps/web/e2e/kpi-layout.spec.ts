import {test,expect} from '@playwright/test';

const context='/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T22:00:00#machine-block';
test('laptop KPIs use two compact rectangular panels and keep references and help usable',async({page})=>{
  await page.goto(context);
  const panels=page.locator('.machine-kpi-panels > .page-panel');
  await expect(panels).toHaveCount(2);
  for(const width of [1366,1920]){
    await page.setViewportSize({width,height:1100});
    await expect.poll(()=>panels.evaluateAll(nodes=>{
      const [a,b]=nodes.map(node=>node.getBoundingClientRect());
      return Math.max(Math.abs(a.y-b.y),Math.abs(a.height-b.height));
    })).toBeLessThan(2);
    for(const panel of await panels.all()){
      const box=(await panel.boundingBox())!;
      expect(box.height).toBeLessThan(340);
      expect(box.width/box.height).toBeGreaterThan(1.3);
    }
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
  await expect(panels.first().getByRole('heading',{name:'Удельный расход энергии',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Ориентиры УРЭ',exact:true})).toHaveCount(0);
  await expect(panels.first().getByText('Цель ППД-2035',{exact:true})).toBeVisible();
  await panels.last().getByRole('button',{name:'Пояснение: КПД агрегата',exact:true}).focus();
  await expect(page.getByRole('tooltip')).toBeVisible();
  await page.setViewportSize({width:390,height:1000});
  await expect.poll(async()=>{
    const a=(await panels.first().boundingBox())!,b=(await panels.last().boundingBox())!;
    return b.y-a.y-a.height;
  }).toBeGreaterThanOrEqual(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
