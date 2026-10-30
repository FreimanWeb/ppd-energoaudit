import {test,expect} from '@playwright/test';

const context='/?object=kns54an&aggregate=НА-1&day=2026-09-29&timestamp=2026-09-29T23:30:00';
const number=(value:number)=>new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(value);

test('annual and investment views stay inside the selected measure and retain its ID',async({page})=>{
  const forecastRequests:unknown[]=[];
  page.on('request',request=>{if(request.url().endsWith('/measures') && request.postDataJSON()?.basis==='forecast') forecastRequests.push(request.postDataJSON());});
  const response=page.waitForResponse(r=>r.url().endsWith('/measures') && r.request().postDataJSON()?.basis==='annual');
  await page.goto(context+'#measures');
  const data=await (await response).json();
  const chosen=data.annual.find((row:{measure_id:string})=>row.measure_id==='throttle_down');
  expect(chosen).toBeTruthy();
  await expect(page.getByText('Расширенный расчёт экономики машинного блока',{exact:true})).toHaveCount(0);
  await expect(page.getByText('Годовой реестр мероприятий',{exact:true})).toHaveCount(0);
  await expect(page.getByLabel('Горизонт экономики')).toHaveCount(0);
  expect(forecastRequests).toHaveLength(0);
  await page.locator(`[data-action-id="annual:${chosen.measure_id}"]`).getByRole('link',{name:/Подробнее/}).click();
  const detail=page.getByRole('region',{name:'Мероприятие',exact:true});
  await expect(detail).toHaveAttribute('data-action-id','annual:'+chosen.measure_id);
  await expect(detail.getByRole('button',{name:'Годовой эффект',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(detail.getByText(new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(chosen.energy_saving_kwh)+' кВт·ч/год',{exact:true})).toBeVisible();
  expect(forecastRequests).toHaveLength(0);
  await detail.getByRole('button',{name:'Инвестиционная оценка',exact:true}).click();
  await expect(detail.getByRole('group',{name:'Накопленный денежный эффект',exact:true})).toBeVisible();
  const updated=page.waitForResponse(r=>r.url().endsWith('/measures') && r.request().postDataJSON()?.horizon_years===2 && r.request().postDataJSON()?.discount_rate===.2);
  await detail.getByLabel('Горизонт экономики').fill('2');
  await detail.getByLabel('Ставка дисконтирования').fill('20');
  const forecast=await (await updated).json();
  const horizon=forecast.horizon.find((row:{measure_id:string})=>row.measure_id===chosen.measure_id);
  await expect(detail.locator('.page-kpis > div').filter({hasText:'NPV, тыс. ₽'}).locator('strong')).toHaveText(number(horizon.npv_krub));
  await detail.getByText('Годовой денежный поток',{exact:true}).click();
  await expect(detail.getByRole('table').first().locator('tbody tr')).toHaveCount(2);
  expect(new URL(page.url()).searchParams.get('measure')).toBe('annual:'+chosen.measure_id);
  await detail.getByRole('button',{name:'Годовой эффект',exact:true}).click();
  await expect(detail.getByRole('group',{name:'Накопленный денежный эффект',exact:true})).toHaveCount(0);
  await expect(detail.getByText(new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(chosen.energy_saving_kwh)+' кВт·ч/год',{exact:true})).toBeVisible();
  await page.reload();
  await expect(detail).toHaveAttribute('data-action-id','annual:'+chosen.measure_id);
  await expect(detail.getByRole('heading',{name:chosen.name,exact:true})).toBeVisible();
  await page.setViewportSize({width:390,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('investment evaluation never substitutes another measure or accepts an invalid horizon',async({page})=>{
  let omit=false;
  await page.route('**/measures',async route=>{
    const response=await route.fetch(),data=await response.json();
    if(route.request().postDataJSON()?.basis==='forecast' && omit) data.horizon=data.horizon.filter((row:{measure_id:string})=>row.measure_id!=='throttle_down');
    await route.fulfill({response,json:data});
  });
  await page.goto(context+'&measure=annual:throttle_down#measures');
  const detail=page.getByRole('region',{name:'Мероприятие',exact:true});
  await expect(detail.getByRole('button',{name:'Годовой эффект',exact:true})).toBeVisible();
  omit=true;
  await detail.getByRole('button',{name:'Инвестиционная оценка',exact:true}).click();
  await expect(detail.getByRole('status')).toContainText('Инвестиционная оценка выбранного мероприятия');
  await expect(detail.getByRole('group',{name:'Накопленный денежный эффект',exact:true})).toHaveCount(0);
  await detail.getByLabel('Горизонт экономики').fill('11');
  await expect(detail.getByRole('alert')).toContainText('целое число от 1 до 10');
});
