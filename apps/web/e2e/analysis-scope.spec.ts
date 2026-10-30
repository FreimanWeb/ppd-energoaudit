import {test,expect} from '@playwright/test';

test('archive context stays independent of a missing aggregate snapshot',async({page})=>{
  const auditRequests:string[]=[];
  page.on('request',request=>{if(/snapshot-audit|snapshots\?/.test(request.url()))auditRequests.push(request.url());});
  await page.goto('/?object=demo-ppd&aggregate=НА-1&day=2020-01-01&timestamp=2020-01-01T00:00:00&well=6#well-history');
  await expect(page.locator('.well-history select')).toHaveValue('6');
  const context=page.getByRole('region',{name:'Контекст анализа',exact:true});
  await expect(context).toContainText('Архив скважины 6');
  await expect(context).toContainText('Независимо от режима НА');
  await expect(page.getByText('Данные непригодны для достоверных выводов',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('combobox',{name:'Агрегат',exact:true})).toHaveCount(0);
  expect(auditRequests).toEqual([]);
  await expect(page.getByRole('heading',{name:'Телеметрия',exact:true})).toHaveCount(0);
});

test('moving from the station to an aggregate makes the scope and time explicit',async({page})=>{
  await page.goto('/?object=demo-ppd#overview');
  const context=page.getByRole('region',{name:'Контекст анализа',exact:true});
  await expect(context).toContainText('Вся станция');
  await page.locator('.sidebar-nav').getByRole('link',{name:'Машинный блок',exact:true}).click();
  await expect(page.getByRole('heading',{name:'КПД',exact:true})).toBeVisible();
  await expect(context).toContainText('НА-1');
  await expect(context).toContainText('Выбранный режим');
  await expect(context.locator('time')).toHaveAttribute('datetime', /T\d{2}:\d{2}:\d{2}$/);
});

test('switching objects clears the well and page-specific intervention',async({page})=>{
  await page.goto('/?object=demo-ppd&well=6&measure=annual:efficiency_recovery_scenario&stage=hall#well-history');
  await expect(page.locator('.well-history select')).toHaveValue('6');
  await page.getByRole('combobox',{name:'Объект',exact:true}).selectOption('kns54an');
  await expect(page.getByRole('heading',{name:'КНС-54',exact:true})).toBeVisible();
  for(const parameter of ['well','measure','stage'])expect(new URL(page.url()).searchParams.has(parameter)).toBe(false);
});
