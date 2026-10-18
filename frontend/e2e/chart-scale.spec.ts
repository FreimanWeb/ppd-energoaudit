import {test,expect} from '@playwright/test';

test('comparison graph has padded data scale and independently switches to zero',async({page})=>{
  await page.goto('/?object=demo-ppd&aggregate=НА-1&start=2026-10-12&end=2026-10-18#timeline');
  const graph=page.getByRole('group',{name:'УРЭ двух периодов',exact:true});
  const svg=graph.getByRole('img',{name:'УРЭ двух периодов',exact:true});
  await expect(svg).toBeVisible();
  const controls=graph.getByRole('group',{name:'Масштаб вертикальной оси',exact:true});
  await expect(controls.getByRole('button',{name:'По данным',exact:true})).toHaveAttribute('aria-pressed','true');
  const domain=async()=> (await svg.getAttribute('data-value-domain'))!.split(',').map(Number);
  const compressed=await domain();
  expect(compressed[0]).toBeGreaterThan(0);expect(compressed[0]).toBeLessThan(4.5);expect(compressed[1]).toBeGreaterThan(5.2);
  await controls.getByRole('button',{name:'От нуля',exact:true}).click();
  await expect.poll(async()=> (await domain())[0]).toBe(0);
  await controls.getByRole('button',{name:'По данным',exact:true}).click();
  await expect.poll(domain).toEqual(compressed);
  const history=page.getByRole('group',{name:'Удельный расход энергии',exact:true});
  await expect(history.getByRole('button',{name:'По данным',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.setViewportSize({width:320,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  await controls.getByRole('button',{name:'От нуля',exact:true}).focus();
  await page.keyboard.press('Enter');
  await expect.poll(async()=> (await domain())[0]).toBe(0);
});

test('compressed scale labels a grid division below and above all visible curves',async({page})=>{
  await page.route('**/api/objects/*/timeline*',route=>route.fulfill({json:{
    object_id:'demo-ppd',aggregate_id:'НА-1',start:'2026-10-01',end:'2026-10-02',interval_hours:2,basis:'interval',latest_at:'2026-10-02T00:00:00',aggregates:[{code:'НА-1',role:'рабочий'}],observations:[],notes:[],
    points:[0,1].map(i=>({timestamp:`2026-10-0${i+1}T00:00:00`,basis:'interval',quality:'ready',snapshot_timestamp:null,power_kw:100,flow_m3h:20,sec_kwh_m3:i?5.2:4.5,sec_calc_kwh_m3:3.8,sec_optimal_kwh_m3:3.45})),
  }}));
  await page.goto('/?object=demo-ppd&aggregate=НА-1#timeline');
  const chart=page.getByRole('group',{name:'Удельный расход энергии',exact:true});
  const ticks=async()=>chart.locator('.visx-axis-y .visx-axis-tick text').allTextContents();
  await expect.poll(async()=> (await ticks()).length).toBeGreaterThan(1);
  const values=(await ticks()).map(v=>Number(v.replace(',','.')));
  expect(Math.min(...values)).toBeLessThan(3.45);
  expect(Math.max(...values)).toBeGreaterThan(5.2);
});
