import { test, expect } from '@playwright/test';

async function fixture(page: import('@playwright/test').Page) {
  await page.setViewportSize({width:1440,height:1000});
  await page.route('**/snapshot-audit', async route => {
    const response=await route.fetch(), audit=await response.json();
    audit.audit.metrics.p_electric_kw=687.39;
    audit.losses=[
      {name:'Полезная мощность',power_kw:309.67,share:.4505,category:'полезная'},
      {name:'Потери КПД',power_kw:377.72,share:.5495,category:'потеря'},
    ];
    await route.fulfill({response,json:audit});
  });
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29&timestamp=2026-09-29T12:00:00#losses');
  await expect(page.locator(".page-panel:not(:has(.network-losses))").getByRole('group',{name:'Декомпозиция мощности',exact:true})).toBeVisible();
}

test('loss tooltips show original power and share once in all three modes',async({page})=>{
  await fixture(page);
  await expect(page.getByLabel('Составляющая потерь')).toHaveCount(0);
  async function compact(plot: import('@playwright/test').Locator) {
    const tip=plot.getByRole('status');
    await expect(tip.getByText('Полезная мощность',{exact:true})).toHaveCount(1);
    await expect(tip.locator('b')).toHaveText('309,67 кВт');
    expect(await tip.locator('b').evaluate(element=>getComputedStyle(element).marginLeft)).toBe('0px');
    await expect(tip.getByText('45,05 %',{exact:true})).toBeVisible();
    await expect(tip.locator('.native-chart-tooltip-swatch')).toHaveCount(0);
  }
  let plot=page.locator(".page-panel:not(:has(.network-losses))").getByRole('group',{name:'Декомпозиция мощности',exact:true});
  const useful=plot.getByRole('button',{name:/^Полезная мощность:/});
  await useful.hover(); await compact(plot);
  expect(await useful.evaluate(el=>getComputedStyle(el).stroke)).toMatch(/transparent|rgba\(0, 0, 0, 0\)|none/);
  await useful.click();
  await expect(page.getByLabel('Разбор составляющей')).toContainText('Полезная мощность');
  await expect(page.getByLabel('Предлагаемые мероприятия')).toHaveCount(0);
  await page.locator('.page-panel:not(:has(.network-losses))').getByRole('button',{name:'Поток мощности',exact:true}).click();
  plot=page.locator(".page-panel:not(:has(.network-losses))").getByRole('group',{name:'Поток мощности',exact:true});
  await plot.getByRole('button',{name:'Полезная мощность',exact:true}).hover();
  await compact(plot);
  await expect(plot.locator('.flow-node title,.flow-link title')).toHaveCount(0);
  await page.locator('.page-panel:not(:has(.network-losses))').getByRole('button',{name:'Структура, %',exact:true}).click();
  plot=page.locator(".page-panel:not(:has(.network-losses))").getByRole('group',{name:'Структура мощности, %',exact:true});
  await plot.getByRole('button',{name:/^Полезная мощность:/}).hover();
  await compact(plot);
  await page.screenshot({path:'/tmp/ppd-loss-compact-tooltip.png',fullPage:true});
});

test('clicking a loss shows concrete proposed actions with calculated effect',async({page})=>{
  await fixture(page);
  await page.locator(".page-panel:not(:has(.network-losses))").getByRole('group',{name:'Декомпозиция мощности',exact:true}).getByRole('button',{name:/^Потери КПД:/}).click();
  const proposals=page.getByLabel('Предлагаемые мероприятия');
  await expect(proposals).toContainText('восстановление КПД');
  await expect(proposals).toContainText('Расчётный эффект');
  await expect(proposals).toContainText('CAPEX требует оценки');
  await expect(page.locator('main')).not.toContainText('связи этой составляющей');
  await page.locator('.page-panel:not(:has(.network-losses))').getByRole('button',{name:'Поток мощности',exact:true}).click();
  await page.locator(".page-panel:not(:has(.network-losses))").getByRole('group',{name:'Поток мощности',exact:true}).getByRole('button',{name:'Потери КПД',exact:true}).press('Enter');
  await expect(proposals).toContainText('восстановление КПД');
});

test('single-series measure bars omit a repeated graph name and do not invent a percentage',async({page})=>{
  await fixture(page);
  await page.locator('nav a[href="#measures"]').click();
  await expect(page.getByText('Годовой реестр мероприятий',{exact:true})).toBeVisible();
  await page.getByText('Сравнить годовую экономию',{exact:true}).click();
  const plot=page.getByRole('group',{name:'Годовой эффект мероприятий',exact:true});
  await page.waitForLoadState('networkidle');
  await plot.locator('.visx-bar').first().focus();
  const tip=plot.getByRole('status');
  await expect(tip.locator('strong')).toContainText('восстановление КПД');
  await expect(tip.locator('b')).toContainText('тыс. кВт·ч/год');
  await expect(tip.getByText('Годовой эффект мероприятий',{exact:true})).toHaveCount(0);
  await expect(tip.locator('.chart-tooltip-share')).toHaveCount(0);
});
