import {test,expect,type Locator} from '@playwright/test';

const context='/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T22:00:00';

async function labelsFit(plot:Locator){
  await expect.poll(()=>plot.evaluate(element=>{
    const root=element.querySelector<SVGSVGElement>('svg.visx-chart')!.getBoundingClientRect();
    const texts=[...element.querySelectorAll<SVGTextElement>('.visx-axis-x text,.chart-category-group text')];
    if(!root.height || !texts.length || texts.some(text=>!text.getBoundingClientRect().height)) return Infinity;
    return Math.max(...texts.map(text=>text.getBoundingClientRect().bottom-root.bottom));
  })).toBeLessThanOrEqual(-1);
}

test('chain loss captions fit after resizing and zooming',async({page})=>{
    await page.goto(context+'#losses');
    const plot=page.getByRole('group',{name:'Декомпозиция мощности',exact:true});
    await expect(plot.locator('.visx-bar').first()).toBeVisible();
    for(const detailed of [false,true]){
      if(detailed) await page.getByRole('button',{name:'Детализация',exact:true}).click();
      for(const width of [2048,1366,1920,390]){
        await page.setViewportSize({width,height:1100});
        await page.evaluate(()=>document.fonts.ready);
        await labelsFit(plot);
      }
      await page.setViewportSize({width:2048,height:1100});
      await page.evaluate(()=>{document.body.style.zoom='1.25';});
      await labelsFit(plot);
      await page.evaluate(()=>{document.body.style.zoom='';});
    }
});

