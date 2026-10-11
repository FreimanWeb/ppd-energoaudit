import { test, expect } from '@playwright/test';

test('telemetry shares real sample cursor and viewport, and selects only available snapshots', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  const day = '2026-09-29';
  const times = ['00:00:00', '00:07:00', '00:30:00', '01:00:00'].map(time => `${day}T${time}`);
  await page.route('**/api/objects/kns54an/telemetry?*', route => route.fulfill({ json: {
    records: [],
    series: [
      { metric: 'P_вх', unit: 'МПа', points: times.map((timestamp, i) => ({ timestamp, value: i === 2 ? null : 2 + i })) },
      { metric: 'P_эл', unit: 'кВт', points: times.map((timestamp, i) => ({ timestamp, value: 600 + i * 20 })) },
      { metric: 'Q', unit: 'м³/ч', points: times.map((timestamp, i) => ({ timestamp, value: 100 + i })) },
    ],
  } }));
  await page.goto(`/?object=kns54an&aggregate=НА-1&day=${day}&timestamp=${times[0]}#telemetry`);
  const charts = page.locator('main svg.visx-chart');
  await expect(charts).toHaveCount(3);
  const first = charts.first();
  await first.focus();
  await first.press('Home');
  await expect(page.locator('main .visx-crosshair')).toHaveCount(3);
  await first.press('ArrowRight');
  for (const crosshair of await page.locator('main .visx-crosshair').all())
    await expect(crosshair).toHaveAttribute('data-timestamp', String(new Date(times[1]).getTime()));
  await first.press('Enter');
  await expect(page).toHaveURL(/#telemetry$/); // 00:07 is a sample, but not an available calculation snapshot.

  const handle = page.locator('main .visx-brush-handle-right').first();
  const bounds = await handle.boundingBox();
  expect(bounds).toBeTruthy();
  await page.mouse.move(bounds!.x + bounds!.width / 2, bounds!.y + bounds!.height / 2);
  await page.mouse.down();
  await page.mouse.move(bounds!.x - 150, bounds!.y + bounds!.height / 2, { steps: 10 });
  await page.mouse.up();
  await expect(page.getByRole('button', { name: 'Весь период', exact: true })).toBeVisible();
  const zoom = await first.getAttribute('data-time-domain');
  for (const chart of await charts.all()) await expect(chart).toHaveAttribute('data-time-domain', zoom!);
  expect(zoom).not.toBe(`${new Date(times[0]).getTime()},${new Date(times[3]).getTime()}`);
  await page.getByRole('button', { name: 'Весь период', exact: true }).click();
  for (const chart of await charts.all()) await expect(chart).toHaveAttribute('data-time-domain', `${new Date(times[0]).getTime()},${new Date(times[3]).getTime()}`);
  await first.focus();
  await first.press('Home');
  await first.press('ArrowRight');
  await first.press('ArrowRight');
  await first.press('Enter');
  await expect(page).toHaveURL(/#snapshot$/);
  expect(new URL(page.url()).searchParams.get('timestamp')).toBe(times[2]);
});

test('period sample resolves a real snapshot on another day', async ({page}) => {
  const timestamp='2026-09-28T12:00:00';
  await page.route('**/api/objects/kns54an/telemetry?*', route => route.fulfill({json:{records:[],series:[{metric:'P_эл',unit:'кВт',points:[{timestamp,value:600},{timestamp:'2026-09-29T12:00:00',value:620}]}]}}));
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29&timestamp=2026-09-29T12:00:00#telemetry');
  await expect(page.getByRole('group',{name:'P_эл',exact:true}).locator('svg.visx-chart')).toBeVisible();
  await page.getByLabel('Режим телеметрии').selectOption('period');
  await page.getByLabel('Начало периода').fill('2026-09-28');
  await page.getByLabel('Конец периода').fill('2026-09-29');
  const plot=page.getByRole('group',{name:'P_эл',exact:true}).locator('svg.visx-chart');
  await expect(plot).toBeVisible();
  await plot.focus();
  await plot.press('Home');
  await plot.press('Enter');
  await expect(page).toHaveURL(/#snapshot$/);
  expect(new URL(page.url()).searchParams.get('day')).toBe('2026-09-28');
  expect(new URL(page.url()).searchParams.get('timestamp')).toBe(timestamp);
});

test('late period snapshot lookup cannot overwrite a newly selected aggregate', async ({page}) => {
  const timestamp='2026-09-28T12:00:00';
  await page.route('**/api/objects/kns54an/telemetry?*', route => route.fulfill({json:{records:[],series:[{metric:'P_эл',unit:'кВт',points:[{timestamp,value:600},{timestamp:'2026-09-29T12:00:00',value:620}]}]}}));
  let release!:()=>void, started!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve;}), pending=new Promise<void>(resolve=>{started=resolve;});
  await page.route('**/aggregates/**/snapshots?day=2026-09-28', async route=>{
    const response=await route.fetch();
    started();
    await gate;
    await route.fulfill({response});
  });
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29&timestamp=2026-09-29T12:00:00#telemetry');
  await expect(page.getByRole('group',{name:'P_эл',exact:true}).locator('svg.visx-chart')).toBeVisible();
  await page.getByLabel('Режим телеметрии').selectOption('period');
  const plot=page.getByRole('group',{name:'P_эл',exact:true}).locator('svg.visx-chart');
  await expect(plot).toBeVisible();
  await plot.focus(); await plot.press('Home'); await plot.press('Enter');
  await pending;
  await page.getByLabel('Агрегат',{exact:true}).selectOption('НА-2');
  const completed=page.waitForResponse(response=>response.url().includes('snapshots?day=2026-09-28'));
  release(); await completed; await page.waitForLoadState('networkidle');
  expect(new URL(page.url()).searchParams.get('aggregate')).toBe('НА-2');
  expect(new URL(page.url()).searchParams.get('day')).toBe('2026-09-29');
  await expect(page).toHaveURL(/#telemetry$/);
});
