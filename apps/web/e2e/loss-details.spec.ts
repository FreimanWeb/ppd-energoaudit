import {test,expect} from '@playwright/test';

test('chain displays BG as an intermediate total in the waterfall',async({page})=>{
  await page.setViewportSize({width:1600,height:1000});
  const response=page.waitForResponse(r=>r.url().endsWith('/network-losses'));
  await page.goto('/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T22:00:00#losses');
  const data=await (await response).json();
  expect(data.status).toBe('scenario');
  const panel=page.locator('.network-losses');
  const total=panel.locator('.network-balance-totals > div').filter({has:page.getByText('Гидравлическая мощность на БГ',{exact:true})});
  await expect(total.locator('dd')).toHaveText(`${new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(data.operator_balance.bg_kw)} кВт`);
  const plot=panel.getByRole('group',{name:'Декомпозиция мощности',exact:true});
  const bg=plot.getByRole('button',{name:/^(Мощность на БГ|Гидравлическая мощность на БГ):/});
  await expect(bg).toHaveCount(1);
  await bg.focus();
  const tooltip=plot.getByRole('status');
  await expect(tooltip).toContainText('Гидравлическая мощность на БГ');
  await expect(tooltip.locator('b')).toContainText(new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(data.operator_balance.bg_kw));
  await panel.getByRole('button',{name:'Структура, %',exact:true}).click();
  await expect(panel.getByRole('group',{name:'Структура мощности, %',exact:true})).toBeVisible();
  await expect(panel.getByText('Сумма составляющих превышает 100%',{exact:false})).toHaveCount(0);
});

test('chain loss opens its dedicated detail and preserves the selected mode',async({page})=>{
  await page.goto('/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T22:00:00#losses');
  const plot=page.locator('.network-losses').getByRole('group',{name:'Декомпозиция мощности',exact:true});
  await plot.getByRole('button',{name:/^Потери при номинальном КПД:/}).click();
  await expect.poll(()=>new URL(page.url()).hash).toBe('#loss-detail');
  expect(new URL(page.url()).searchParams.get('timestamp')).toBe('2026-10-18T22:00:00');
  await expect(page.getByLabel('Предлагаемые мероприятия')).toBeVisible();
});




test('chain summary has eight bars and detail restores equipment losses with its own boundary',async({page})=>{
  await page.setViewportSize({width:1600,height:1000});
  const response=page.waitForResponse(r=>r.url().endsWith('/network-losses'));
  await page.goto('/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T22:00:00#losses');
  const data=await (await response).json();
  const panel=page.locator('.network-losses');
  const plot=panel.getByRole('group',{name:'Декомпозиция мощности',exact:true});
  await expect(plot.locator('.visx-bar')).toHaveCount(8);
  await expect(plot.getByRole('button',{name:/^Потери в преобразователе частоты:/})).toHaveCount(0);
  await expect(plot.getByRole('button',{name:/^Трение в стволах скважин:/})).toHaveCount(0);
  await expect(plot.getByRole('button',{name:/^Потери при номинальном КПД:/})).toBeVisible();
  await expect(panel.getByLabel('Потери по участкам цепочки')).toContainText('% потребления');
  const endpoint=panel.locator('.network-balance-totals > div').filter({has:page.getByText('Полезная гидравлическая мощность на устьях скважин',{exact:true})});
  await expect(endpoint.locator('dd')).toHaveText(`${new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(data.operator_balance.output_kw)} кВт`);
  await panel.getByRole('button',{name:'Детализация',exact:true}).click();
  await expect(plot.locator('.visx-bar')).toHaveCount(12);
  await expect(plot.getByRole('button',{name:/^Потери в преобразователе частоты:/})).toHaveCount(1);
  await expect(plot.getByRole('button',{name:/^Трение в стволах скважин:/})).toHaveCount(1);
  await expect(panel.getByLabel('Потери по участкам цепочки')).toContainText('% потерь');
  await expect(panel.getByText('Полезная гидравлическая мощность на устьях скважин',{exact:true})).toHaveCount(0);
  await expect(panel.getByText('Полезная гидравлическая мощность',{exact:true})).toBeVisible();
  await panel.getByRole('button',{name:'Структура, %',exact:true}).click();
  await panel.getByRole('button',{name:'Свернуть детализацию',exact:true}).click();
  await expect(panel.getByRole('group',{name:'Структура мощности, %',exact:true})).toBeVisible();
  await expect(panel.getByText('Сумма составляющих превышает 100%',{exact:false})).toHaveCount(0);
  await expect(panel.getByRole('button',{name:'Поток мощности',exact:true})).toHaveCount(0);
});
