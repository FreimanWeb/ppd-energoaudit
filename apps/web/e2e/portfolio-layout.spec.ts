import {test, expect} from '@playwright/test';

test('card view shows four objects in one desktop row with readable content',async({page})=>{
  for(const width of [1280,1600,2560]){
    await page.setViewportSize({width,height:1000});
    await page.goto('/');
    await expect(page.locator('.portfolio-card')).toHaveCount(4);
    const boxes=await page.locator('.portfolio-card').evaluateAll(cards=>cards.map(card=>{
      const box=card.getBoundingClientRect();return {x:box.x,y:box.y,width:box.width};
    }));
    expect(new Set(boxes.map(box=>Math.round(box.y))).size).toBe(1);
    expect(boxes[3].x).toBeGreaterThan(boxes[2].x);
    expect(await page.locator('.portfolio-card').evaluateAll(cards=>cards.every(card=>card.scrollWidth<=card.clientWidth))).toBe(true);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
});

test('compact cards and detailed rows share filters and data without refetching', async ({page}) => {
  await page.setViewportSize({width:1600,height:1000});
  const requests:string[] = [];
  page.on('request', request => {
    if (request.url().includes('/api/monitoring/')) requests.push(request.url());
  });
  const today = new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Moscow'}).format(new Date());
  await page.route('**/api/monitoring/objects?**', route => route.fulfill({json:{
    generated_at:`${today}T12:00:00`,interval_hours:2,
    objects:['kns54an','demo-ppd'].map((code,index)=>({
      code,name:index ? 'Демо · КНС':'КНС-54',ngdu_name:'НГДУ',water_type:'пресная',status:'unknown',comparison_status:'normal',data_status:'stale',latest_at:`${today}T00:00:00`,kpi_at:`${today}T00:00:00`,basis:'daily',sec_kwh_m3:3,efficiency:null,change_pct:index ? 0.004 : -0.004,history:[],note:'Подробное основание: исходные данные требуют проверки по истории.',
    })),
  }}));
  await page.route('**/api/monitoring/history?**', route => route.fulfill({json:{objects:['kns54an','demo-ppd'].map(code=>({code,history:[{timestamp:`${today}T00:00:00`,value:3},{timestamp:`${today}T02:00:00`,value:3.2}]}))}}));
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Карточки',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('.portfolio-sparkline')).toHaveCount(2);
  const card = page.locator('.portfolio-card').first();
  expect((await card.boundingBox())!.height).toBeLessThanOrEqual(460);
  const compactGraphHeight = (await card.locator('.portfolio-sparkline-frame').boundingBox())!.height;
  await expect(card.locator('.portfolio-badge')).toContainText('неизвестно');
  await expect(card.locator('.portfolio-freshness')).toContainText('Данные устарели');
  await expect(card.locator('.portfolio-card-note')).toBeHidden();
  for (const item of await page.locator('.portfolio-card').all()) {
    await expect(item.locator('.portfolio-change strong')).toHaveText('0 %');
    await expect(item.locator('.portfolio-change')).toHaveClass('portfolio-change');
  }
  await page.getByRole('searchbox').fill('КНС-54');
  await expect(page.locator('.portfolio-card')).toHaveCount(1);
  const beforeSwitch = [...requests];
  await page.getByRole('button',{name:'Строки',exact:true}).click();
  await expect(page.getByRole('button',{name:'Строки',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('searchbox')).toHaveValue('КНС-54');
  await expect(card.locator('.portfolio-card-note')).toBeVisible();
  const details = (await card.locator('.portfolio-card-details').boundingBox())!;
  const graph = (await card.locator('.portfolio-card-chart').boundingBox())!;
  expect(graph.x).toBeGreaterThanOrEqual(details.x + details.width);
  expect((await card.locator('.portfolio-sparkline-frame').boundingBox())!.height).toBeGreaterThan(compactGraphHeight);
  expect((await card.boundingBox())!.width).toBeGreaterThan(1400);
  expect(requests).toEqual(beforeSwitch);
  const point = card.locator('.portfolio-sparkline circle').first();
  await point.hover();
  await expect(page.locator('.portfolio-point-tooltip')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button',{name:'Строки',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.getByRole('button',{name:'Открыть историю: КНС-54',exact:true}).click();
  await expect.poll(()=>new URL(page.url()).hash).toBe('#timeline');
});

test('row graph keeps its space while history loads and shows errors without losing metadata', async ({page}) => {
  await page.setViewportSize({width:1600,height:1000});
  let release!:()=>void;
  const waiting = new Promise<void>(resolve=>{release=resolve;});
  await page.route('**/api/monitoring/history?**', async route=>{
    await waiting;
    await route.fulfill({status:503,json:{detail:'История временно недоступна.'}});
  });
  try {
    await page.goto('/');
    await expect(page.getByLabel('Загрузка истории УРЭ')).toHaveCount(4);
    await page.getByRole('button',{name:'Строки',exact:true}).click();
    const card = page.locator('.portfolio-card').first();
    const before = (await card.boundingBox())!;
    const skeleton = (await card.locator('.portfolio-history-skeleton').boundingBox())!;
    const details = (await card.locator('.portfolio-card-details').boundingBox())!;
    expect(skeleton.x).toBeGreaterThanOrEqual(details.x+details.width);
    release();
    await expect(card.getByRole('alert')).toHaveText('История временно недоступна.');
    const after = (await card.boundingBox())!;
    expect(Math.abs(after.height-before.height)).toBeLessThan(2);
    await expect(card.locator('.portfolio-reading')).toBeVisible();
    await expect(card.getByRole('button',{name:/Открыть историю/})).toBeEnabled();
    await page.getByRole('button',{name:'Карточки',exact:true}).click();
    await expect(card.getByRole('alert')).toHaveText('История временно недоступна.');
  } finally {
    release();
  }
});
