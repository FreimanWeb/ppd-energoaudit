import {test,expect,type Locator} from '@playwright/test';
import {lossLabels} from '../src/shared/lossLabels';

const context='/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T22:00:00';

async function labelsFit(plot:Locator){
  await expect.poll(()=>plot.evaluate(element=>{
    const root=element.querySelector<SVGSVGElement>('svg.visx-chart')!.getBoundingClientRect();
    const texts=[...element.querySelectorAll<SVGTextElement>('.visx-axis-x text,.chart-category-group text')];
    if(!root.height || !texts.length || texts.some(text=>!text.getBoundingClientRect().height)) return Infinity;
    return Math.max(...texts.map(text=>text.getBoundingClientRect().bottom-root.bottom));
  })).toBeLessThanOrEqual(-1);
}

test('complete loss captions fit the real SVG after resizing and zooming in both maps',async({page})=>{
  for(const section of ['machine-losses','losses']){
    await page.goto(context+'#'+section);
    const plot=page.getByRole('group',{name:'Декомпозиция мощности',exact:true});
    await expect(plot.locator('.visx-bar').first()).toBeVisible();
    for(const detailed of [false,true]){
      if(detailed) await page.getByRole('button',{name:section==='machine-losses'?'Детализация потерь НА':'Детализация',exact:true}).click();
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
  }
});

test('scheme, aggregate map, chain map, tooltips and tables use the same loss names',async({page})=>{
  await page.setViewportSize({width:1920,height:1100});
  await page.goto(context+'#overview');
  await expect(page.locator('.loss-flow-article[data-power]')).toHaveCount(6);
  for(const id of ['nominal','efficiency','pump_bg','friction','local','choke'] as const){
    const card=page.locator(`.loss-flow-article[data-loss="${id}"]`);
    await expect(card.locator('.loss-flow-article-label')).toHaveText(lossLabels[id]);
    expect(await card.evaluate(element=>element.scrollHeight<=element.clientHeight)).toBe(true);
  }
  for(const section of ['machine-losses','losses']){
    await page.goto(context+'#'+section);
    const plot=page.getByRole('group',{name:'Декомпозиция мощности',exact:true});
    const bar=plot.locator('.visx-bar').nth(1);
    await expect(bar).toHaveAttribute('aria-label',new RegExp('^'+lossLabels.nominal+':'));
    await bar.hover();
    await expect(plot.getByRole('status').locator('strong')).toHaveText(lossLabels.nominal);
    if(section==='machine-losses'){
      await page.getByText('Таблица составляющих',{exact:true}).click();
      await expect(page.getByRole('table').filter({hasText:lossLabels.nominal})).toBeVisible();
    }else{
      await page.goto(context+'#network-scenario');
      await page.getByText('Составляющие и основания расчёта',{exact:true}).click();
      await expect(page.getByRole('table').filter({hasText:lossLabels.friction})).toBeVisible();
      await expect(page.getByRole('table').filter({hasText:lossLabels.vfd})).toHaveCount(0);
    }
  }
});
