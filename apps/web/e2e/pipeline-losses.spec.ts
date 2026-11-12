import {test,expect} from '@playwright/test';

const query='/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T22:00:00#pipelines';
const number=(value:number)=>new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(value);

test('pipeline disclosures show sections and connected wells without counting shared friction twice',async({page})=>{
  await page.setViewportSize({width:1600,height:1000});
  const response=page.waitForResponse(r=>r.url().endsWith('/network-losses'));
  await page.goto(query);
  const data=await (await response).json();
  expect(data.status).toBe('scenario');
  const region=page.getByRole('region',{name:'Потери по трубопроводам',exact:true});
  const ids=[...new Set<string>(data.segments.map((s:{pipeline_id:string})=>s.pipeline_id))];
  await expect(region.locator('.pipeline-loss-row')).toHaveCount(ids.length);
  let sum=0;
  for(const id of ids){
    const own=data.segments.filter((s:{pipeline_id:string})=>s.pipeline_id===id);
    const direct=data.wells.filter((w:{path_pipeline_ids:string[]})=>w.path_pipeline_ids.at(-1)===id);
    const friction=own.reduce((sum:number,s:{power_kw:number})=>sum+s.power_kw,0);
    const local=direct.reduce((sum:number,w:{armature_loss_kw:number})=>sum+w.armature_loss_kw,0);
    const choke=direct.reduce((sum:number,w:{choke_loss_kw:number})=>sum+w.choke_loss_kw,0);
    const summary=region.locator(`details[data-pipeline="${id}"] > summary`);
    await expect(summary.locator(':scope > strong')).toHaveText([friction,local,choke,friction+local+choke].map(number));
    sum+=friction+local+choke;
  }
  const expected=data.segments.reduce((sum:number,s:{power_kw:number})=>sum+s.power_kw,0)+data.wells.reduce((sum:number,w:{armature_loss_kw:number;choke_loss_kw:number})=>sum+w.armature_loss_kw+w.choke_loss_kw,0);
  expect(sum).toBeCloseTo(expected,6);
  const shared=ids.find(id=>data.wells.filter((w:{path_pipeline_ids:string[]})=>w.path_pipeline_ids.includes(id)).length>1)!;
  expect(shared).toBeTruthy();
  const row=region.locator(`details[data-pipeline="${shared}"]`);
  await row.locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(row).toHaveAttribute('open','');
  await expect(row.getByRole('heading',{name:'Собственные участки',exact:true})).toBeVisible();
  await expect(row.getByRole('heading',{name:'Подключённые скважины',exact:true})).toBeVisible();
  await expect(row.getByText(/не повторяется в итогах ответвлений/)).toBeVisible();
  await expect(row.getByRole('table').last().locator('tbody tr')).toHaveCount(data.wells.filter((w:{path_pipeline_ids:string[]})=>w.path_pipeline_ids.includes(shared)).length);
  await page.setViewportSize({width:390,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await row.locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(row).not.toHaveAttribute('open','');
});

test('unknown choking and unassigned wells remain explicit',async({page})=>{
  const response=await page.request.post('/api/objects/demo-ppd/aggregates/НА-1/network-losses',{data:{source:'telemetry',day:'2026-10-18',timestamp:'2026-10-18T22:00:00'}});
  expect(response.ok()).toBe(true);
  const data=await response.json();
  const affected=data.wells.find((w:{path_pipeline_ids:string[]})=>w.path_pipeline_ids.length>0);
  const id=affected.path_pipeline_ids.at(-1);
  affected.choke_loss_kw=null;
  affected.deficit_mpa=1;
  const unassigned=data.wells.find((w:{id:string})=>w.id!==affected.id);
  unassigned.path_pipeline_ids=[];
  unassigned.synthetic_connection=true;
  data.status='infeasible';
  await page.route('**/network-losses',route=>route.fulfill({json:data}));
  await page.goto(query);
  const row=page.locator(`.pipeline-loss-row[data-pipeline="${id}"]`);
  await expect(row.locator('summary > strong').nth(2)).toHaveText('—');
  await expect(row.locator('summary > strong').nth(3)).toHaveText('—');
  await row.locator('summary').click();
  await expect(row.getByRole('status')).toContainText('не определены');
  await expect(page.getByRole('region',{name:'Скважины без привязки',exact:true})).toContainText(unassigned.id);
  data.status='unavailable';
  await page.reload();
  await expect(page.locator('.pipeline-loss-row')).toHaveCount(0);
  await page.unrouteAll({behavior:'wait'});
});
