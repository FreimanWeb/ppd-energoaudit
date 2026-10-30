import {test,expect} from '@playwright/test';

test('measure list separates units and explains the scope of combined hydraulic actions',async({page})=>{
  await page.goto('/?object=demo-ppd#measures');
  const annual=page.getByRole('region',{name:'Годовая экономия электроэнергии',exact:true});
  const power=page.getByRole('region',{name:'Снижение электрической мощности',exact:true});
  await expect(annual).toBeVisible();
  await expect(power).toBeVisible();
  await expect(annual).toContainText('кВт·ч/год');
  await expect(power).not.toContainText('кВт·ч/год');
  await expect(power).toContainText('включает настройку напора');
  expect((await annual.boundingBox())!.y).toBeLessThan((await power.boundingBox())!.y);
  await power.locator('[data-action-id="network:clean_pipes"]').getByRole('link',{name:/Подробнее/}).click();
  const detail=page.getByRole('region',{name:'Мероприятие',exact:true});
  await expect(detail).toContainText('Что меняем');
  await expect(detail).toContainText('База сравнения');
  await expect(detail).toContainText('Граница эффекта');
  await expect(detail).toContainText('До реализации');
  await expect(detail).toContainText('одного выбранного НА');
  await expect(detail).toContainText('характеристик');
  await expect(detail).toContainText('Эффекты альтернативных мероприятий не суммируются');
  await expect(detail.getByText('Электрический ввод до', {exact:true})).toBeVisible();
  await expect(detail.getByText('Электрический ввод после', {exact:true})).toBeVisible();
});

test('hydraulic diagnostics precede the proposed actions',async({page})=>{
  await page.goto('/?object=demo-ppd#network-scenario');
  const basis=page.getByText('Составляющие и основания расчёта',{exact:true});
  const actions=page.getByRole('region',{name:'Мероприятия внешней сети',exact:true});
  await expect(basis).toBeVisible();
  await expect(actions).toBeVisible();
  expect((await basis.boundingBox())!.y).toBeLessThan((await actions.boundingBox())!.y);
});
