import {test,expect} from '@playwright/test';

test('report groups expand below the scheme, retain arithmetic and link highlighting',async({page})=>{
  await page.goto('/?object=demo-ppd#overview');
  const scheme=page.getByRole('region',{name:'Условная технологическая схема ППД',exact:true});
  const flow=scheme.locator('.loss-flow');
  await expect(flow).toBeVisible();
  await expect(flow.locator('[data-stage="hall"] .loss-flow-parent .loss-flow-value')).not.toHaveText('Нет оценки');
  await expect(scheme.locator('svg .scheme-loss-marker')).toHaveCount(0);
  const canvas=(await scheme.locator('.equipment-scheme').boundingBox())!;
  expect((await flow.boundingBox())!.y).toBeGreaterThanOrEqual(canvas.y+canvas.height);
  await expect(scheme.getByRole('heading',{name:'Граф потерь',exact:true})).toHaveCount(0);
  await expect(scheme.locator('.scheme-leaders path')).toHaveCount(3);
  const equipment=scheme.locator('.equipment-scheme');
  const naturalRatio=await equipment.evaluate(el=>{const svg=el as SVGSVGElement;return svg.viewBox.baseVal.width/svg.viewBox.baseVal.height;});
  expect(canvas.width/canvas.height).toBeCloseTo(naturalRatio,1);
  await expect(scheme.locator('.scheme-canvas .loss-flow')).toHaveCount(1);
  await expect(flow.getByText('Потреблённая мощность',{exact:true})).toBeHidden();
  await flow.getByText('Баланс мощности',{exact:true}).click();
  await expect(flow.getByText('Потреблённая мощность',{exact:true})).toBeVisible();
  await flow.getByText('Баланс мощности',{exact:true}).click();
  expect((await flow.locator('.loss-flow-parent').first().boundingBox())!.height).toBeLessThan(150);
  for(const id of ['hall','pipes','wells']){
    const node=flow.locator(`.loss-flow-stage[data-stage="${id}"]`);
    const toggle=node.getByRole('button',{name:/Состав потерь/});
    await expect(toggle).toHaveAttribute('aria-expanded','false');
    await toggle.hover();
    await expect(scheme.locator(`.scheme-area-link[data-stage="${id}"]`)).toHaveAttribute('data-active','true');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded','true');
    await expect(node.locator('.loss-flow-children')).toBeVisible();
    await expect.poll(()=>scheme.evaluate((element,id)=>{
      const path=element.querySelector(`.scheme-leaders path[data-stage="${id}"]`) as SVGPathElement;
      const canvas=element.querySelector('.scheme-canvas')!.getBoundingClientRect();
      const area=element.querySelector(`.scheme-area-link[data-stage="${id}"] rect`)!.getBoundingClientRect();
      const card=element.querySelector(`.loss-flow-stage[data-stage="${id}"] .loss-flow-parent`)!.getBoundingClientRect();
      const start=path.getPointAtLength(0),end=path.getPointAtLength(path.getTotalLength());
      if(Math.abs(start.x-end.x)>1) return Infinity;
      return Math.max(Math.abs(start.x-(area.x+area.width/2-canvas.x)),Math.abs(start.y-(area.bottom-canvas.y)),Math.abs(end.x-(card.x+card.width/2-canvas.x)),Math.abs(end.y-(card.top-canvas.y)));
    },id)).toBeLessThan(1);
    const parent=(await node.locator('.loss-flow-parent').boundingBox())!;
    const children=await node.locator('[data-child-power]').all();
    const boxes=await Promise.all(children.map(child=>child.boundingBox()));
    for(const box of boxes){
      expect(box!.y).toBeGreaterThan(parent.y+parent.height);
      expect(box!.y).toBeCloseTo(boxes[0]!.y,0);
    }
    for(let i=1;i<boxes.length;i++) expect(boxes[i]!.x).toBeGreaterThan(boxes[i-1]!.x+boxes[i-1]!.width);
    const values=await node.evaluate(node=>({
      total:Number(node.getAttribute('data-power')),
      children:[...node.querySelectorAll('[data-child-power]')].map(child=>Number(child.getAttribute('data-child-power'))),
    }));
    expect(values.children.reduce((sum,n)=>sum+n,0)).toBeCloseTo(values.total,6);
    await expect(node.getByRole('link',{name:'Подробнее',exact:true})).toBeVisible();
  }
  await expect(flow.locator('[data-stage="hall"] .loss-flow-children')).toContainText('Номинальные потери НА');
  await expect(flow.locator('[data-stage="hall"] .loss-flow-children')).toContainText('Потери из-за снижения КПД');
  await expect(flow.locator('[data-stage="hall"] .loss-flow-children')).toContainText('Насос–БГ');
  await expect(flow.locator('[data-stage="wells"] .loss-flow-children')).toContainText('Штуцирование');
  for(const width of [1280,390]){
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
  const hall=flow.locator('[data-stage="hall"]');
  await hall.getByRole('button',{name:/Состав потерь/}).focus();
  await page.keyboard.press('Enter');
  await expect(hall.getByRole('button',{name:/Состав потерь/})).toHaveAttribute('aria-expanded','false');
  await hall.getByRole('link',{name:'Подробнее',exact:true}).click();
  expect(new URL(page.url()).hash).toBe('#machine-block');
});

test('unavailable graph expands without inventing values',async({page})=>{
  const response=await page.request.post('/api/objects/demo-ppd/station-summary',{data:{source:'telemetry'}});
  expect(response.ok()).toBe(true);
  const data=await response.json();
  await page.route('**/station-summary',route=>route.fulfill({json:{...data,network:{status:'unavailable',warnings:[]}}}));
  await page.goto('/?object=demo-ppd#overview');
  const flow=page.locator('.loss-flow');
  await expect(flow.locator('.loss-flow-stage')).toHaveCount(3);
  await expect(flow.locator('.loss-flow-parent .loss-flow-value')).toHaveText(['Нет оценки','Нет оценки','Нет оценки']);
  await flow.locator('[data-stage="hall"]').getByRole('button',{name:/Состав потерь/}).click();
  await expect(flow).toContainText('Недостаточно данных для разложения');
  await page.unrouteAll({behavior:'wait'});
});

test('expansion keeps cards in place and keyboard focus frames the whole card',async({page})=>{
  const errors:string[]=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.setViewportSize({width:1800,height:1100});
  await page.goto('/?object=demo-ppd#overview');
  const cards=page.locator('.loss-flow-parent');
  await expect(cards.first().locator('.loss-flow-value')).not.toHaveText('Нет оценки');
  const initial=await cards.evaluateAll(nodes=>nodes.map(node=>{const {x,width}=node.getBoundingClientRect();return {x,width};}));
  for(const card of await cards.all()) expect((await card.boundingBox())!.width).toBeLessThanOrEqual(260);
  for(const toggle of await page.locator('.loss-flow-toggle').all()){
    await toggle.click();
    const current=await cards.evaluateAll(nodes=>nodes.map(node=>{const {x,width}=node.getBoundingClientRect();return {x,width};}));
    expect(current).toEqual(initial);
  }
  for(const child of await page.locator('[data-child-power]').all()) expect((await child.boundingBox())!.width).toBeLessThanOrEqual(152);
  for(const child of await page.locator('[data-child-power]').all()) expect((await child.boundingBox())!.height).toBe(144);
  const hallChildren=page.locator('.loss-flow-stage[data-stage="hall"] [data-child-power]');
  for(const child of await hallChildren.all()) expect((await child.boundingBox())!.width).toBeGreaterThanOrEqual(151);
  const hallLast=(await hallChildren.last().boundingBox())!;
  const pipesFirst=(await page.locator('.loss-flow-stage[data-stage="pipes"] [data-child-power]').first().boundingBox())!;
  expect(hallLast.x+hallLast.width).toBeLessThan(pipesFirst.x);
  const toggle=page.locator('.loss-flow-toggle').last();
  await toggle.focus();
  await page.keyboard.press('Tab');
  await page.keyboard.press('Shift+Tab');
  await expect(toggle).toHaveCSS('outline-style','none');
  await expect(cards.last()).toHaveCSS('outline-style','solid');
  expect(errors).toEqual([]);
});
