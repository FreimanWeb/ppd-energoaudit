import { test, expect } from '@playwright/test';

test('a single power chart spans the row and period controls stay compact', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const times = ['00:00', '06:00', '12:00', '18:00'].map(time => `2026-09-29T${time}:00`);
  await page.route('**/api/objects/kns54an/telemetry?*', route => route.fulfill({ json: {
    records: [], series: [
      { metric: 'P_вх', unit: 'МПа', points: times.map(timestamp => ({ timestamp, value: 2 })) },
      { metric: 'P_эл', unit: 'кВт', points: times.map(timestamp => ({ timestamp, value: 600 })) },
    ],
  } }));
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29#telemetry');
  const pressure = page.getByRole('group', { name: 'Давления', exact: true });
  const power = page.getByRole('group', { name: 'P_эл', exact: true });
  await expect(power.locator('svg.visx-chart')).toBeVisible();
  const pressureBox = await pressure.boundingBox(), powerBox = await power.boundingBox();
  expect(powerBox!.width).toBeCloseTo(pressureBox!.width, 1);
  const track = await pressure.locator('.time-control-track').boundingBox();
  expect(track!.height).toBeLessThanOrEqual(24);
  const handle = await page.getByRole('slider', { name: 'Начало видимого периода', exact: true }).boundingBox();
  expect(handle!.height).toBeGreaterThanOrEqual(24);
});

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
  await first.click({ position: { x: 100, y: 10 } });
  expect(await first.evaluate(node => getComputedStyle(node).outlineWidth)).toBe('0px');
  await expect(page.getByRole('region', { name: 'Управление временем', exact: true })).toBeVisible();
  await expect(page.locator('.time-control-dates time')).toHaveCount(2);
  await first.focus();
  await first.press('Home');
  expect(await first.evaluate(node => getComputedStyle(node).outlineWidth)).toBe('2px');
  await expect(page.locator('main .visx-crosshair')).toHaveCount(3);
  await first.press('ArrowRight');
  for (const crosshair of await page.locator('main .visx-crosshair').all())
    await expect(crosshair).toHaveAttribute('data-timestamp', String(new Date(times[1]).getTime()));
  await first.press('Enter');
  await expect(page).toHaveURL(/#telemetry$/); // 00:07 is a sample, but not an available calculation snapshot.

  const handle = page.getByRole('slider', { name: 'Конец видимого периода', exact: true });
  const bounds = await handle.boundingBox();
  expect(bounds).toBeTruthy();
  await page.mouse.move(bounds!.x + bounds!.width - 6, bounds!.y + bounds!.height / 2);
  await page.mouse.down();
  await page.mouse.move(bounds!.x + bounds!.width - 156, bounds!.y + bounds!.height / 2, { steps: 10 });
  await page.mouse.up();
  await expect(page.getByRole('button', { name: 'Весь период', exact: true })).toBeVisible();
  const zoom = await first.getAttribute('data-time-domain');
  for (const chart of await charts.all()) await expect(chart).toHaveAttribute('data-time-domain', zoom!);
  expect(zoom).not.toBe(`${new Date(times[0]).getTime()},${new Date(times[3]).getTime()}`);
  await page.getByRole('button', { name: 'Весь период', exact: true }).click();
  for (const chart of await charts.all()) await expect(chart).toHaveAttribute('data-time-domain', `${new Date(times[0]).getTime()},${new Date(times[3]).getTime()}`);
  const end = page.getByRole('slider', { name: 'Конец видимого периода', exact: true });
  await end.focus();
  await end.press('ArrowLeft');
  expect(Number(await end.inputValue())).toBeLessThan(new Date(times[3]).getTime());
  const keyboardZoom = await first.getAttribute('data-time-domain');
  for (const chart of await charts.all()) await expect(chart).toHaveAttribute('data-time-domain', keyboardZoom!);
  await end.press('End');
  const begin = page.getByRole('slider', { name: 'Начало видимого периода', exact: true });
  await begin.focus();
  await begin.press('ArrowRight');
  expect(Number(await begin.inputValue())).toBeGreaterThan(new Date(times[0]).getTime());
  await begin.press('Home');
  await expect(page.getByRole('button', { name: 'Весь период', exact: true })).toBeDisabled();
  await first.click({ position: { x: 100, y: 10 } });
  expect(await first.evaluate(node => getComputedStyle(node).outlineWidth)).toBe('0px');
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
