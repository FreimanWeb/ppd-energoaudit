import {test,expect} from '@playwright/test';

const context='/?object=kns54an&aggregate=НА-1&day=2026-09-29&timestamp=2026-09-29T12:00:00';

test('recommendations show addressed diagnostics with reference evidence for the selected regime',async({page})=>{
  const request=page.waitForRequest(r=>r.url().endsWith('/recommendations'));
  await page.goto(context+'#recommendations');
  expect((await request).postDataJSON()).toMatchObject({source:'telemetry',timestamp:'2026-09-29T12:00:00'});
  await expect(page.getByRole('heading',{name:'Рекомендации по насосному агрегату',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Адресная диагностика',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Справочные сведения по агрегату',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Дефекты по журналу 1С ТОИР',exact:true})).toBeVisible();
});

test('reference lists diagnostic rules with their aggregate bindings',async({page})=>{
  await page.goto('/?object=kns54an#reference');
  await expect(page.getByRole('heading',{name:'Справочные материалы',exact:true})).toBeVisible();
  await page.getByText('Правила адресной диагностики насосного агрегата',{exact:true}).click();
  await expect(page.getByRole('table').filter({hasText:'Перепад насос–БГ'})).toBeVisible();
  await expect(page.getByRole('table').filter({hasText:'ЦНС 180-1422(-2)'})).toBeVisible();
});
