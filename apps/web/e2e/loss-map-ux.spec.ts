import { goToSection } from "./helpers";
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
  // Итог цепочки приходит отдельным запросом и сдвигает график: ждём его до наведения.
  const network=page.waitForResponse(r=>r.url().endsWith('/network-losses'));
  await page.goto('/?object=kns54an&aggregate=НА-1&day=2026-09-29&timestamp=2026-09-29T12:00:00#machine-losses');
  await network;
  await expect(page.locator(".page-panel").filter({has:page.getByRole("heading",{name:/^Цифровая карта потерь мощности/})}).getByRole('group',{name:'Декомпозиция мощности',exact:true})).toBeVisible();
}

test('loss tooltips show original power and share once in both modes',async({page})=>{
  await fixture(page);
  await expect(page.getByLabel('Составляющая потерь')).toHaveCount(0);
  async function compact(plot: import('@playwright/test').Locator) {
    const tip=plot.getByRole('status');
    await expect(tip.getByText('Полезная гидравлическая мощность',{exact:true})).toHaveCount(1);
    await expect(tip.locator('b')).toHaveText('309,67 кВт');
    expect(await tip.locator('b').evaluate(element=>getComputedStyle(element).marginLeft)).toBe('0px');
    await expect(tip.getByText('45,05 %',{exact:true})).toBeVisible();
    await expect(tip.locator('.native-chart-tooltip-swatch')).toHaveCount(0);
  }
  let plot=page.locator(".page-panel").filter({has:page.getByRole("heading",{name:/^Цифровая карта потерь мощности/})}).getByRole('group',{name:'Декомпозиция мощности',exact:true});
  const useful=plot.getByRole('button',{name:/^Полезная гидравлическая мощность:/});
  await useful.hover(); await compact(plot);
  expect(await useful.evaluate(el=>getComputedStyle(el).stroke)).toMatch(/transparent|rgba\(0, 0, 0, 0\)|none/);
  await useful.click();
  await expect(page.getByLabel('Разбор составляющей')).toContainText('Полезная гидравлическая мощность');
  await expect(page.getByLabel('Предлагаемые мероприятия')).toHaveCount(0);
  await page.locator(".page-panel").filter({has:page.getByRole("heading",{name:/^Цифровая карта потерь мощности/})}).getByRole('button',{name:'Структура, %',exact:true}).click();
  plot=page.locator(".page-panel").filter({has:page.getByRole("heading",{name:/^Цифровая карта потерь мощности/})}).getByRole('group',{name:'Структура мощности, %',exact:true});
  await plot.getByRole('button',{name:/^Полезная гидравлическая мощность:/}).hover();
  await compact(plot);
  await page.screenshot({path:'/tmp/ppd-loss-compact-tooltip.png',fullPage:true});
});

test('clicking a loss shows concrete proposed actions with calculated effect',async({page})=>{
  await fixture(page);
  await page.locator(".page-panel").filter({has:page.getByRole("heading",{name:/^Цифровая карта потерь мощности/})}).getByRole('group',{name:'Декомпозиция мощности',exact:true}).getByRole('button',{name:/^Потери из-за снижения КПД/}).click();
  await expect.poll(()=>new URL(page.url()).hash).toBe('#loss-detail');
  const proposals=page.getByLabel('Предлагаемые мероприятия');
  await expect(proposals).toContainText('восстановление КПД');
  await expect(proposals).toContainText('Расчётный эффект');
  await expect(proposals).toContainText('CAPEX требует оценки');
  await expect(page.locator('main')).not.toContainText('связи этой составляющей');
  await page.goBack();
  await expect(page.locator(".page-panel").filter({has:page.getByRole("heading",{name:/^Цифровая карта потерь мощности/})}).getByRole('group',{name:'Декомпозиция мощности',exact:true})).toBeVisible();
  await page.locator(".page-panel").filter({has:page.getByRole("heading",{name:/^Цифровая карта потерь мощности/})}).getByRole('button',{name:'Структура, %',exact:true}).click();
  await page.locator(".page-panel").filter({has:page.getByRole("heading",{name:/^Цифровая карта потерь мощности/})}).getByRole('group',{name:'Структура мощности, %',exact:true}).getByRole('button',{name:/^Потери из-за снижения КПД[^:]*:/}).press('Enter');
  await expect.poll(()=>new URL(page.url()).hash).toBe('#loss-detail');
  await expect(proposals).toContainText('восстановление КПД');
});

test('category labels wrap without ellipsis and stay within the chart on a narrow screen',async({page})=>{
  await fixture(page);
  await page.setViewportSize({width:390,height:1000});
  const plot=page.locator(".page-panel").filter({has:page.getByRole("heading",{name:/^Цифровая карта потерь мощности/})}).getByRole('group',{name:'Декомпозиция мощности',exact:true});
  const input=plot.locator('.visx-axis-x text').filter({hasText:'Потреблённая'});
  await expect.poll(async()=> (await input.locator('tspan').allTextContents()).join(' ')).toBe('Потреблённая мощность');
  expect(await plot.locator('.visx-axis-x text').evaluateAll(labels=>labels.some(label=>label.querySelectorAll('tspan').length>1))).toBe(true);
  expect(await plot.locator('.visx-axis-x').textContent()).not.toContain('…');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const bounds=(await plot.locator('svg.visx-chart').boundingBox())!;
  for(const label of await plot.locator('.visx-axis-x text').all()){
    const box=(await label.boundingBox())!;
    expect(box.y+box.height).toBeLessThanOrEqual(bounds.y+bounds.height);
  }
});
