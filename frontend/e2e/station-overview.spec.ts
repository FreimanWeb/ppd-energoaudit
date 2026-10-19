import {test,expect} from '@playwright/test';
import {goToSection} from './helpers';

test('overview is station-wide, shows both demo pumps, and puts annual estimates before the scheme',async({page})=>{
  const response=page.waitForResponse(r=>r.url().endsWith('/station-summary'));
  await page.goto('/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T23:30:00#overview');
  const summary=await (await response).json();
  expect(summary.aggregate_count).toBe(2);expect(summary.included_aggregates).toEqual(['НА-1','НА-2']);expect(summary.complete).toBe(true);
  expect(summary.metrics.flow_m3h).toBeGreaterThan(200);expect(summary.network.status).toBe('scenario');
  await expect(page.getByLabel('Агрегат',{exact:true})).toHaveCount(0);
  await expect(page.locator('.station-kpis .metric-card')).toHaveCount(4);
  const losses=page.locator('.station-kpis .metric-card').filter({hasText:'Потери до устьев · оценка'});
  await expect(losses.locator('strong')).toHaveText(new Intl.NumberFormat('ru-RU',{maximumFractionDigits:1}).format(summary.network.operator_balance.total_loss_kw));
  await expect(page.locator('.station-context')).toContainText('Учтено НА: 2 из 2');
  await expect(page.locator('.station-kpis')).not.toContainText('НА в расчёте');
  await expect(page.locator('.equipment-node[data-node^="pump-"]')).toHaveCount(2);
  await expect(page.locator(".scheme-panel .is-largest")).toHaveCount(0);
  const hall=page.getByRole('link',{name:'Открыть машинный блок',exact:true}).locator('rect').first();
  expect(await hall.getAttribute('fill')).toBe('var(--surface-subtle)');
  const annual=page.getByRole('heading',{name:/^Годовая оценка/});
  await expect(annual).toBeVisible();
  const a=await annual.boundingBox(),scheme=await page.locator('.scheme-panel').boundingBox();
  expect(a!.y).toBeLessThan(scheme!.y);
  await expect(page.getByRole('navigation',{name:'Вкладки: Обзор'}).getByRole('link',{name:'Прогноз закачки',exact:true})).toHaveCount(0);
  const again=page.waitForResponse(r=>r.url().endsWith('/station-summary'));
  await page.goto('/?object=demo-ppd&aggregate=НА-2#overview');
  expect((await (await again).json()).metrics).toEqual(summary.metrics);
  await page.setViewportSize({width:320,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});

test('machine loss map belongs to the machine block and redundant history return is absent',async({page})=>{
  await page.goto('/?object=demo-ppd&aggregate=НА-1#machine-block');
  await expect(page.getByRole('heading',{name:/^Цифровая карта потерь мощности/})).toHaveCount(0);
  await page.getByRole('navigation',{name:'Вкладки: Машинный блок',exact:true}).getByRole('link',{name:'Карта потерь',exact:true}).click();
  await expect(page.getByRole('heading',{name:/^Цифровая карта потерь мощности/})).toBeVisible();
  await expect(page.getByLabel('Агрегат',{exact:true}).locator('option')).toHaveCount(2);
  await goToSection(page,'losses');
  await expect(page.getByRole('heading',{name:/^Цифровая карта потерь мощности/})).toHaveCount(0);
  await expect(page.getByRole('link',{name:'← Вернуться к истории объекта',exact:true})).toHaveCount(0);
  await goToSection(page,'forecast');
  await expect(page.getByRole('navigation',{name:'Вкладки: Скважины',exact:true})).toBeVisible();
});
