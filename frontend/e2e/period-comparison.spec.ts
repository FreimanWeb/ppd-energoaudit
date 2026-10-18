import {test,expect} from '@playwright/test';

test('period comparison follows the charts and persists a manual baseline',async({page})=>{
  await page.goto('/?object=demo-ppd&aggregate=НА-1&start=2026-10-12&end=2026-10-18#timeline');
  const panel=page.locator('.page-panel').filter({has:page.getByRole('heading',{name:/^Сравнение периодов/})});
  await expect(panel.getByLabel('Начало базового периода')).toHaveValue('2026-10-05');
  await expect(panel.getByLabel('Конец базового периода')).toHaveValue('2026-10-11');
  await expect(panel.locator('.comparison-selected')).toContainText('12.10.2026 — 18.10.2026');
  await expect(panel.locator('.comparison-table')).toContainText('УРЭ по парным замерам');
  await expect(panel.locator('.comparison-state')).toContainText('Сопоставимость не подтверждена');
  await expect(page.getByText('Что проверить',{exact:true})).toHaveCount(0);
  await panel.getByLabel('Начало базового периода').fill('2026-10-01');
  await expect.poll(()=>new URL(page.url()).searchParams.get('base_start')).toBe('2026-10-01');
  await page.reload();
  await expect(panel.getByLabel('Начало базового периода')).toHaveValue('2026-10-01');
  await panel.getByRole('button',{name:'Предыдущий период',exact:true}).click();
  await expect(panel.getByLabel('Начало базового периода')).toHaveValue('2026-10-05');
  await page.locator('input[aria-label="Начало периода"]').fill('2026-10-15');
  await expect(panel.getByLabel('Начало базового периода')).toHaveValue('2026-10-11');
  await expect(panel.getByLabel('Конец базового периода')).toHaveValue('2026-10-14');
  await page.setViewportSize({width:320,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});

test('invalid and overlapping baselines are explicit; changing charts does not use stale comparison',async({page})=>{
  await page.goto('/?object=demo-ppd&aggregate=НА-1&start=2026-10-12&end=2026-10-18&base_start=2026-10-20&base_end=2026-10-01#timeline');
  await expect(page.getByRole('alert')).toContainText('Начало должно быть не позже конца');
  await expect(page.locator('.comparison-table')).toHaveCount(0);
  await page.getByLabel('Начало базового периода').fill('2026-10-12');
  await page.getByLabel('Конец базового периода').fill('2026-10-18');
  await expect(page.getByText(/Периоды пересекаются/)).toBeVisible();
  await page.locator('input[aria-label="Начало периода"]').fill('');
  await expect(page.locator('.comparison-table')).toHaveCount(0);
});

test('daily comparison uses matched energy and volume sums rather than endpoint ratios',async({page})=>{
  await page.route('**/api/objects/*/timeline*',route=>{
    const query=new URL(route.request().url()).searchParams;
    const baseline=query.get('start')==='2026-10-01';
    const start=baseline?'2026-10-01':'2026-10-03',end=baseline?'2026-10-02':'2026-10-04';
    const points=[start,end].map((day,i)=>({timestamp:day+'T00:00:00',basis:'daily',quality:'ready',snapshot_timestamp:null,energy_kwh:100,volume_m3:baseline?100:i===0?10:100,sec_kwh_m3:baseline?1:i===0?10:1}));
    return route.fulfill({json:{object_id:'demo-ppd',aggregate_id:'НА-1',start,end,interval_hours:2,basis:'daily',latest_at:end+'T00:00:00',points,aggregates:[{code:'НА-1',role:'рабочий'}],observations:[],notes:[]}});
  });
  await page.goto('/?object=demo-ppd&aggregate=НА-1&start=2026-10-03&end=2026-10-04#timeline');
  const guide=page.locator('.comparison-guide');
  await expect(guide.locator('ol')).not.toBeVisible();
  await guide.locator('summary').press('Enter');
  await expect(guide.locator('li')).toHaveCount(3);
  await expect(guide.locator('ol')).toBeVisible();
  const graph=page.getByRole('group',{name:'УРЭ двух периодов',exact:true});
  await expect(graph.getByRole('img',{name:'УРЭ двух периодов',exact:true})).toBeVisible();
  await expect(graph.getByRole('button',{name:'А · База',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(graph.getByRole('button',{name:'Б · Выбрано',exact:true})).toHaveAttribute('aria-pressed','true');
  const svg=graph.getByRole('img',{name:'УРЭ двух периодов',exact:true});
  await svg.hover({position:{x:80,y:70}});
  await expect(page.locator('.native-chart-tooltip')).toContainText('01.10.2026');
  await expect(page.locator('.native-chart-tooltip')).toContainText('03.10.2026');
  await expect(page.locator('.native-chart-tooltip strong')).toHaveCSS('white-space','pre-line');
  await expect(graph).toHaveCSS('overflow','visible');
  await expect(graph.locator('.native-chart-stage')).toHaveCSS('overflow','visible');
  await expect.poll(()=>graph.locator('.visx-grid-x line').count()).toBeGreaterThan(1);
  const labels=await graph.locator('.visx-axis-x .visx-axis-tick text').allTextContents();
  expect(labels.some(label=>/\d{2}\.\d{2}/.test(label))).toBe(true);
  expect(labels.every(label=>!label.includes(':'))).toBe(true);
  const bounds=await svg.boundingBox();
  await svg.hover({position:{x:bounds!.width-30,y:bounds!.height-60}});
  const clipping=await page.locator('.native-chart-tooltip').evaluate(element=>{
    const result=[];
    for(let node=element.parentElement;node;node=node.parentElement) if(/hidden|clip/.test(getComputedStyle(node).overflow)) result.push(node.className || node.tagName);
    return result;
  });
  expect(clipping).toEqual([]);
  const tip=await page.locator('.native-chart-tooltip').boundingBox();
  expect(tip!.x).toBeGreaterThanOrEqual(0);
  expect(tip!.y).toBeGreaterThanOrEqual(0);
  expect(tip!.x+tip!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  expect(tip!.y+tip!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  const timeline=page.getByRole('group',{name:'Удельный расход энергии',exact:true});
  const timelineLabels=await timeline.locator('.visx-axis-x .visx-axis-tick text').allTextContents();
  expect(timelineLabels.every(label=>!label.includes(':'))).toBe(true);
  const row=page.locator('.comparison-table tbody tr').filter({hasText:'УРЭ по суммам'});
  await expect(row.locator('td')).toHaveText(['УРЭ по суммам, кВт·ч/м³','1','1,82','81,8']);
  await expect(page.getByLabel('Полнота данных')).toContainText('2 / 2');
});
