import {test,expect} from '@playwright/test';

for(const width of [1800,1280]){
  test(`KPI references stay visible, muted and separated at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:1000});
    await page.goto('/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T22:00:00#machine-block');
    const panels=page.locator('.machine-kpi-panels > .page-panel');
    await expect(panels).toHaveCount(2);
    await expect(panels.locator('h2')).toHaveText(['Удельный расход энергии','КПД']);
    await expect(page.getByRole('button',{name:'Ориентиры УРЭ',exact:true})).toHaveCount(0);
    await expect(panels.first().getByText('Оптимальный',{exact:true})).toBeVisible();
    await expect(panels.first().getByText('Цель ППД-2035',{exact:true})).toBeVisible();
    const secondary=page.locator('.machine-kpi-secondary,.machine-efficiency > .metric-group');
    await expect(secondary).toHaveCount(2);
    const boundaries=[];
    for(const row of await secondary.all()){
      await expect(row).toHaveCSS('border-top-width','1px');
      const color=await row.evaluate(element=>getComputedStyle(element).color);
      for(const text of await row.locator('strong,.metric-unit,.metric-segment-label,.metric-label').all()) await expect(text).toHaveCSS('color',color);
      const box=(await row.boundingBox())!;
      const panel=(await row.locator('xpath=ancestor::section[contains(@class,"page-panel")]').boundingBox())!;
      expect(box.width/panel.width).toBeGreaterThan(.9);
      boundaries.push(box.y);
    }
    expect(Math.abs(boundaries[0]-boundaries[1])).toBeLessThan(2);
    const primary=panels.first().locator('.machine-ure > .metric-values strong').first();
    expect(await primary.evaluate(element=>getComputedStyle(element).color)).not.toBe(await secondary.first().evaluate(element=>getComputedStyle(element).color));
  });
}
