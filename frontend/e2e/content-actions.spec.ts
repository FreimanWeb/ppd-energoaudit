import {test,expect} from '@playwright/test';
import {pages} from '../src/app/navigation.mjs';
import {goToSection} from './helpers';

test('snapshot omits redundant footer actions and sidebar navigation retains context',async({page})=>{
  await page.goto('/?object=demo-ppd&aggregate=НА-1&day=2026-10-18#snapshot');
  const calculation=page.locator('.page-panel').filter({has:page.getByRole('heading',{name:'Режимный расчёт',exact:true})});
  await expect(calculation).toBeVisible();
  await expect(calculation.getByRole('link',{name:'Источники данных',exact:true})).toHaveCount(0);
  await expect(calculation.getByRole('link',{name:'Формулы расчёта',exact:true})).toHaveCount(0);
  const daily=page.locator('.page-panel').filter({has:page.getByRole('heading',{name:'Суточный факт',exact:true})});
  await expect(daily.getByRole('link',{name:'Годовая оценка',exact:true})).toHaveCount(0);
  const context=new URL(page.url()).search;
  await goToSection(page,'sources');
  expect(new URL(page.url()).search).toBe(context);
  await expect(page.locator('main .page-panel').first()).toBeVisible();
});

test('operator content has no unstyled text navigation across its pages',async({page})=>{
  for(const {id:route} of pages.filter(page=>page.id!=='portfolio')){
    await page.goto('/?object=demo-ppd&aggregate=НА-1&day=2026-10-18#'+route);
    await expect(page.locator('main .page-panel').first()).toBeVisible();
    await expect(page.locator('main a:not(.ds-button):not(.page-tabs a):not(svg a)')).toHaveCount(0);
    const targets=await page.locator('main a').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('href')));
    for(const href of targets)expect(pages.map(page=>page.id)).toContain(new URL(href!,page.url()).hash.slice(1));
    await page.setViewportSize({width:320,height:844});
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth),{message:route+' fits mobile'}).toBeLessThanOrEqual(320);
    await page.setViewportSize({width:1280,height:720});
  }
});
