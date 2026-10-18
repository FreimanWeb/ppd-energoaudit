import {test,expect} from '@playwright/test';
import {goToSection} from './helpers';

const context='/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T22:00:00';
test('area cards open the same measure detail and retain context after reload',async({page})=>{
  await page.goto(context+'#pipelines');
  const actions=page.getByRole('region',{name:'Мероприятия участка',exact:true});
  const card=actions.locator('[data-action-id]').first();
  await expect(card).toContainText('Очистить трубы');
  const id=await card.getAttribute('data-action-id');
  const name=await card.locator('h4').innerText();
  await card.getByRole('link',{name:/Подробнее/}).click();
  expect(new URL(page.url()).searchParams.get('measure')).toBe(id);
  expect(new URL(page.url()).searchParams.get('timestamp')).toBe('2026-10-18T22:00:00');
  const detail=page.getByRole('region',{name:'Мероприятие',exact:true});
  await expect(detail.getByRole('heading',{name,exact:true})).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.setViewportSize({width:1280,height:720});
  await page.reload();
  await expect(detail.getByRole('heading',{name,exact:true})).toBeVisible();
  await detail.getByRole('button',{name:'Оценить сценарий',exact:true}).click();
  await expect(detail.getByLabel('Результат сценария мероприятия')).toContainText('После');
  await page.getByLabel('Участок мероприятий',{exact:true}).selectOption('hall');
  await expect(page.locator('.action-list [data-stage]:not([data-stage="hall"])')).toHaveCount(0);
  await expect(page.locator('.action-list [data-stage="hall"]').first()).toBeVisible();
});

test('station priorities link to an aggregate at the common station timestamp',async({page})=>{
  await page.goto(context+'#overview');
  const priorities=page.locator('.page-panel').filter({has:page.getByRole('heading',{name:'Приоритетные действия',exact:true})});
  await expect(priorities.locator('[data-action-id]').first()).toBeVisible();
  expect(await priorities.locator('[data-action-id]').count()).toBeLessThanOrEqual(3);
  const stamp=await page.locator('.station-context time').getAttribute('datetime');
  await priorities.getByRole('link',{name:/Подробнее/}).first().click();
  expect(new URL(page.url()).searchParams.get('timestamp')).toBe(stamp);
  await expect(page.getByRole('region',{name:'Мероприятие',exact:true})).toBeVisible();
});

test('chain waterfall groups match their own bars and stay inside the chart',async({page})=>{
  await page.goto(context+'#losses');
  const chart=page.getByRole('group',{name:'Декомпозиция мощности',exact:true});
  await expect(chart.locator('.chart-category-group')).toHaveCount(3);
  await expect(chart.locator('.chart-category-group text')).toHaveText(['Машинный блок','Трубопроводы','Скважины и арматура']);
  for(const group of await chart.locator('.chart-category-group').all()){
    const geometry=await group.evaluate(group=>{
      const svg=group.closest('svg')!,start=group.getAttribute('data-from'),end=group.getAttribute('data-to');
      const first=(svg.querySelector(`.visx-bar[aria-label^="${start}:"]`) as SVGGraphicsElement).getBBox();
      const last=(svg.querySelector(`.visx-bar[aria-label^="${end}:"]`) as SVGGraphicsElement).getBBox();
      const brace=(group.querySelector('path') as SVGGraphicsElement).getBBox();
      const box=(group as SVGGElement).getBBox();
      return {start:brace.x-first.x,end:brace.x+brace.width-last.x-last.width,bottom:box.y+box.height,height:Number(svg.getAttribute('height'))-24};
    });
    expect(Math.abs(geometry.start)).toBeLessThan(.1);
    expect(Math.abs(geometry.end)).toBeLessThan(.1);
    expect(geometry.bottom).toBeLessThanOrEqual(geometry.height);
  }
  await page.setViewportSize({width:390,height:844});
  await expect(chart.locator('.chart-category-group')).toHaveCount(3);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('CRM aggregate forecast is hidden from the operator tabs but its URL works',async({page})=>{
  await page.goto(context+'#wells');
  await expect(page.locator('.page-tabs a[href$="#crm"]')).toHaveCount(0);
  await page.goto(context+'#crm');
  await expect(page.getByRole('heading',{name:/CRM станции/})).toBeVisible();
  await goToSection(page,'wells');
});
