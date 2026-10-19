import {test,expect} from '@playwright/test';

test('six visible expense articles sit below the scheme with process groups below them',async({page})=>{
  await page.setViewportSize({width:1800,height:1100});
  const response=page.waitForResponse(r=>r.url().endsWith('/station-summary'));
  await page.goto('/?object=demo-ppd#overview');
  const data=await (await response).json(),balance=data.network.operator_balance;
  const scheme=page.getByRole('region',{name:'Условная технологическая схема ППД',exact:true});
  const cards=scheme.locator('.loss-flow-article');
  await expect(cards).toHaveCount(6);
  await expect(scheme.locator('.loss-flow-toggle,.loss-flow-children')).toHaveCount(0);
  await expect(scheme.locator('.loss-flow-group')).toHaveText(['Машинный блок и обвязка до БГ','От БГ до устьев скважин']);
  const expected=[...balance.groups.find((g:{id:string})=>g.id==='hall').children.map((c:{power_kw:number})=>c.power_kw),...balance.groups.find((g:{id:string})=>g.id==='pipes').children.map((c:{power_kw:number})=>c.power_kw),balance.groups.find((g:{id:string})=>g.id==='wells').power_kw];
  for(let i=0;i<expected.length;i++) await expect(cards.nth(i)).toHaveAttribute('data-power',String(expected[i]));
  expect(expected.reduce((sum:number,n:number)=>sum+n,0)).toBeCloseTo(balance.total_loss_kw,6);
  const card=(await cards.first().boundingBox())!,groups=(await scheme.locator('.loss-flow-groups').boundingBox())!,equipment=(await scheme.locator('.equipment-scheme').boundingBox())!;
  expect(groups.y).toBeGreaterThanOrEqual(card.y+card.height);
  expect(card.y).toBeGreaterThan(equipment.y+equipment.height);
  expect(card.height).toBeLessThanOrEqual(160);
  await cards.first().hover();
  await expect(scheme.locator('.scheme-area-link[data-stage="hall"]')).toHaveAttribute('data-active','true');
  await expect(scheme.locator('.loss-flow-article[data-stage="hall"][data-active]')).toHaveCount(3);
  await cards.last().hover();
  await expect(scheme.locator('.loss-flow-article[data-stage="pipes"][data-active]')).toHaveCount(3);
  await expect(scheme.locator('.scheme-loss-anchor[data-loss="choke"]')).toHaveAttribute('data-stage','pipes');
  await cards.last().focus();
  await page.keyboard.press('Enter');
  expect(new URL(page.url()).hash).toBe('#pipelines');
});

test('each leader reaches its own expense card and diagram point after resize',async({page})=>{
  await page.goto('/?object=demo-ppd#overview');
  const scheme=page.getByRole('region',{name:'Условная технологическая схема ППД',exact:true});
  await expect(scheme.locator('.scheme-leaders path')).toHaveCount(6);
  for(const width of [1800,1280,390]){
    await page.setViewportSize({width,height:1000});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await expect.poll(()=>scheme.evaluate(element=>{
      const canvas=element.querySelector('.scheme-canvas')!.getBoundingClientRect();
      return Math.max(...[...element.querySelectorAll<SVGPathElement>('.scheme-leaders path')].map(path=>{
        const id=path.getAttribute('data-loss');
        const anchor=element.querySelector(`.scheme-loss-anchor[data-loss="${id}"]`)!.getBoundingClientRect();
        const card=element.querySelector(`.loss-flow-article[data-loss="${id}"]`)!.getBoundingClientRect();
        const start=path.getPointAtLength(0),end=path.getPointAtLength(path.getTotalLength());
        return Math.max(Math.abs(start.x-(card.x+card.width/2-canvas.x)),Math.abs(start.y-(card.top-canvas.y)),Math.abs(end.x-(anchor.x+anchor.width/2-canvas.x)),Math.abs(end.y-(anchor.y+anchor.height/2-canvas.y)));
      }));
    })).toBeLessThan(1);
  }
  await scheme.locator('.loss-flow-article[data-loss="friction"]').click();
  expect(new URL(page.url()).hash).toBe('#pipelines');
});

test('unavailable articles do not invent power or percentages',async({page})=>{
  const response=await page.request.post('/api/objects/demo-ppd/station-summary',{data:{source:'telemetry'}});
  const data=await response.json();
  await page.route('**/station-summary',route=>route.fulfill({json:{...data,network:{status:'unavailable',warnings:[]}}}));
  await page.goto('/?object=demo-ppd#overview');
  await expect(page.locator('.loss-flow-article .loss-flow-value')).toHaveText(Array(6).fill('Нет оценки'));
  await expect(page.locator('.loss-flow-article .loss-flow-share')).toHaveText(Array(6).fill(''));
  await page.unrouteAll({behavior:'wait'});
});
