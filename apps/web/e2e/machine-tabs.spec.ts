import {test,expect} from '@playwright/test';
import {goToSection} from './helpers';

const context='/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T22:00:00';

test('machine tabs separate indicators and the loss map and preserve analysis context',async({page})=>{
  const networkRequests:string[]=[];
  page.on('request',request=>{if(request.url().endsWith('/network-losses')) networkRequests.push(request.url());});
  await page.goto(context+'#machine-block');
  const tabs=page.getByRole('navigation',{name:'Вкладки: Машинный блок',exact:true});
  await expect(tabs.getByRole('link')).toHaveText(['Показатели','Карта потерь','Рабочая точка']);
  await expect(tabs.getByRole('link',{name:'Показатели',exact:true})).toHaveAttribute('aria-current','page');
  await expect(page.locator('.machine-kpi-panels')).toBeVisible();
  await expect(page.getByRole('heading',{name:/^Годовая оценка/})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Режим машинного блока',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'История КПД машинного блока',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:/^Цифровая карта потерь мощности/})).toHaveCount(0);
  expect(networkRequests).toHaveLength(0);
  const before=new URL(page.url()).search;
  const response=page.waitForResponse(r=>r.url().endsWith('/network-losses'));
  await tabs.getByRole('link',{name:'Карта потерь',exact:true}).click();
  const data=await (await response).json();
  expect(new URL(page.url()).hash).toBe('#machine-losses');
  expect(new URL(page.url()).search).toBe(before);
  await expect(page.getByRole('group',{name:'Декомпозиция мощности',exact:true})).toBeVisible();
  await expect(page.locator('.machine-kpi-panels')).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'История КПД машинного блока',exact:true})).toHaveCount(0);
  const summary=page.getByLabel('Итог выбранного участка',{exact:true});
  await expect(summary.locator('dd').last()).toHaveText(`${new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(data.total_loss_kw)} кВт`);
  const details=page.locator('details.metric-disclosure').filter({has:page.getByText('Детализация по оборудованию и основания расчёта',{exact:true})});
  await expect(details).not.toHaveAttribute('open','');
  await expect(details.getByRole('table').first()).not.toBeVisible();
  await details.locator(':scope > summary').click();
  await expect(details.getByRole('table').first()).toBeVisible();
  await expect(details.getByRole('table').first()).toContainText('Основание расчёта');
  await page.reload();
  await expect(tabs.getByRole('link',{name:'Карта потерь',exact:true})).toHaveAttribute('aria-current','page');
  await page.setViewportSize({width:390,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await tabs.getByRole('link',{name:'Показатели',exact:true}).click();
  await expect(page.locator('.machine-kpi-panels')).toBeVisible();
  expect(new URL(page.url()).search).toBe(before);
});

test('loss inspection and measure links open the dedicated machine loss map',async({page})=>{
  await page.goto(context+'#machine-block');
  const card=page.locator('.annual-group .metric-card').filter({has:page.getByText('Потери по КПД',{exact:true})});
  await card.getByLabel('Разобрать: Потери по КПД',{exact:true}).click();
  await card.getByRole('link',{name:'Потери',exact:true}).click();
  expect(new URL(page.url()).hash).toBe('#machine-losses');
  await expect(page.getByLabel('Разбор составляющей',{exact:true})).toContainText('Потери из-за снижения КПД');
  await page.goto(context+'&measure=annual:efficiency_recovery_scenario#measures');
  const detail=page.getByRole('region',{name:'Мероприятие',exact:true});
  await detail.getByRole('link',{name:'Разобрать потери участка',exact:true}).click();
  expect(new URL(page.url()).hash).toBe('#machine-losses');
  expect(new URL(page.url()).searchParams.get('timestamp')).toBe('2026-10-18T22:00:00');
  await expect(page.getByRole('group',{name:'Декомпозиция мощности',exact:true})).toBeVisible();
});

test('machine loss map remains available in field-trip mode',async({page})=>{
  await page.goto('/?object=demo-ppd&aggregate=НА-1&mode=field_trip#machine-losses');
  await expect(page.getByRole('group',{name:'Декомпозиция мощности',exact:true})).toBeVisible();
  await expect(page.getByLabel('Момент измерения',{exact:true})).toHaveCount(0);
  await goToSection(page,'machine-block');
  await expect(page.locator('.machine-kpi-panels')).toBeVisible();
  expect(new URL(page.url()).searchParams.get('mode')).toBe('field_trip');
});
