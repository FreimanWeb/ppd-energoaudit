import { test, expect } from '@playwright/test';

const fixture='/?object=kns54an&aggregate=НА-1&day=2026-09-29&timestamp=2026-09-29T12%3A00%3A00#machine-block';
test('metric evidence retains the measurement and opens related sources and formulas', async ({page})=>{
 await page.goto(fixture);
 const fact=page.locator('.station-kpis .metric-card').filter({has:page.getByText('УРЭ за сутки',{exact:true})});
 await expect(fact).toBeVisible();
 await page.screenshot({path:'/tmp/ppd-question-overview.png',fullPage:true});
 await fact.getByLabel('Разобрать: УРЭ за сутки',{exact:true}).click();
 await fact.getByRole('link',{name:'Источники',exact:true}).click();
 await expect(page.locator('tr[data-highlighted="true"]')).toHaveCount(2);
 await page.screenshot({path:'/tmp/ppd-question-sources.png',fullPage:true});
 expect(new URL(page.url()).searchParams.get('timestamp')).toBe('2026-09-29T12:00:00');
 await page.getByRole('link',{name:'Формулы показателя',exact:true}).click();
 const selected=page.locator('.formula-card[data-highlighted="true"]');
 await expect(selected).toHaveCount(1);
 await expect(selected.locator('details')).toHaveAttribute('open','');
 await expect(selected).toContainText('(16)');
 await page.reload();
 await expect(page.locator('.formula-card[data-highlighted="true"] details')).toHaveAttribute('open','');
});
test('efficiency deviation leads to its losses and applicable measures without inventing payback',async({page})=>{
 await page.goto(fixture);
 await page.getByRole('link',{name:'Годовая оценка',exact:true}).click();
 const card=page.locator('.annual-group .metric-card').filter({has:page.getByText('Потери по КПД',{exact:true})});
 await card.getByLabel('Разобрать: Потери по КПД',{exact:true}).click();
 await card.getByRole('link',{name:'Потери',exact:true}).click();
 await expect(page).toHaveURL(/inspect=efficiency_loss/);
 await page.getByLabel('Предлагаемые мероприятия').getByRole('link',{name:'Оценить мероприятия',exact:true}).click();
 await expect(page.getByLabel('Связанные мероприятия')).toContainText('восстановление КПД');
 await page.screenshot({path:'/tmp/ppd-question-measures.png',fullPage:true});
 expect(new URL(page.url()).searchParams.get('aggregate')).toBe('НА-1');
 expect(new URL(page.url()).searchParams.get('timestamp')).toBe('2026-09-29T12:00:00');
 await page.getByRole('button',{name:'Показать все мероприятия',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Мероприятия по участкам',exact:true})).toBeVisible();
 await page.locator('[data-action-id="annual:efficiency_recovery_scenario"]').getByRole('link',{name:/Подробнее/}).click();
 await expect(page.getByRole('region',{name:'Мероприятие',exact:true})).toContainText('Требует оценки');
});

test('detailed equipment and causal calculations retain context when returning to the classic map',async({page})=>{
 await page.goto('/?object=knsopu&mode=field_trip&aggregate=НА-1&inspect=pump_loss#formulas');
 await expect(page.getByLabel('Разбор потерь').getByRole('table')).toContainText('Электрическая мощность');
 const decomposition=page.getByLabel('Разложение потерь');
 await decomposition.getByRole('link',{name:'По причинам',exact:true}).click();
 await page.getByLabel('Разбор потерь').getByRole('button',{name:'Перепад гидравлической мощности насос–БГ',exact:true}).click();
 await expect(decomposition.getByRole('link',{name:'По причинам',exact:true})).toHaveAttribute('aria-current','page');
 expect(new URL(page.url()).searchParams.get('inspect')).toBe('hydraulic_bg_loss');
 await page.reload();
 await expect(decomposition.getByRole('link',{name:'По причинам',exact:true})).toHaveAttribute('aria-current','page');
 await page.getByLabel('Уровень причинного разбора').getByRole('link',{name:'Составляющие отклонения КПД',exact:true}).click();
 await page.getByLabel('Разбор потерь').getByRole('button',{name:'Вязкость',exact:true}).click();
 await expect(page).toHaveURL(/inspect=viscosity_loss/);
 await decomposition.getByRole('link',{name:'По оборудованию',exact:true}).click();
 await page.goBack();
 await expect(page).toHaveURL(/inspect=viscosity_loss/);
 await expect(decomposition.getByRole('link',{name:'По причинам',exact:true})).toHaveAttribute('aria-current','page');
 await decomposition.getByRole('link',{name:'По оборудованию',exact:true}).click();
 await page.getByLabel('Разбор потерь').getByRole('button',{name:'Потери в насосе',exact:true}).click();
 await page.getByRole('link',{name:'К карте потерь',exact:true}).click();
 await expect(page.getByRole('group',{name:'Декомпозиция мощности',exact:true})).toBeVisible();
 const context=new URL(page.url()).searchParams;
 expect(context.get('object')).toBe('knsopu');
 expect(context.get('aggregate')).toBe('НА-1');
 expect(context.get('mode')).toBe('field_trip');
 for(const width of [390,1440]){
   await page.setViewportSize({width,height:1000});
   await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(0);
 }
 await page.getByRole('navigation',{name:'Вкладки: Машинный блок',exact:true}).getByRole('link',{name:'Показатели',exact:true}).click();
 await expect(page.getByRole('heading',{name:'КПД',exact:true})).toBeVisible();
 await expect(page.getByRole('group',{name:'Декомпозиция мощности',exact:true})).toHaveCount(0);
});
