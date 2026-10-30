import {test,expect} from '@playwright/test';

for(const objectId of ['kns54an','knsopu','kns97pren']) {
test(`network schematic shows shared pipes once and opens details for ${objectId}`,async({page})=>{
  const response=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/objects/${objectId}/network`);
  await page.goto(`/?object=${objectId}&day=2026-09-29#network`);
  const data=await (await response).json();
  const panel=page.getByRole('region',{name:'Схема водоводов',exact:true});
  await expect(panel).toBeVisible();
  const pipeNames=new Set(data.wells.flatMap((well:{path_pipeline_names:string[]})=>well.path_pipeline_names));
  await expect(panel.locator('[data-kind=pipe]')).toHaveCount(pipeNames.size);
  await expect(panel.locator('[data-kind=well]')).toHaveCount(data.wells.length);
  expect(await panel.locator('[data-kind=source]').evaluateAll(nodes=>nodes.every(node=>(node as SVGGraphicsElement).getBBox().height>0))).toBe(true);
  expect(await panel.locator('.pipeline-schematic-node text').evaluateAll(nodes=>nodes.every(node=>(node as SVGTextElement).getComputedTextLength()<136))).toBe(true);
  const pipe=panel.locator('[data-kind=pipe]').first();
  await pipe.focus();await pipe.press('Enter');
  await expect(panel.getByRole('region',{name:'Параметры выбранного элемента'})).toContainText('Водовод');
  const well=data.wells.find((item:{path_complete:boolean})=>item.path_complete);
  await panel.getByLabel('Найти скважину',{exact:true}).selectOption(well.well);
  await expect(panel.getByRole('region',{name:'Параметры выбранного элемента'})).toContainText('Скв '+well.well);
  await expect(panel.locator('[data-kind=well][aria-pressed=true]')).toHaveCount(1);
  expect(await panel.locator('.pipeline-schematic-edge[data-highlighted=true]').count()).toBeGreaterThan(0);
  const unknown=data.wells.find((item:{path_complete:boolean})=>!item.path_complete);
  if(unknown){
    await panel.getByLabel('Найти скважину',{exact:true}).selectOption(unknown.well);
    await expect(panel.getByRole('region',{name:'Параметры выбранного элемента'})).toContainText('Связь со станцией не подтверждена');
  }
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await panel.getByLabel('Найти скважину',{exact:true}).selectOption('');
  expect(await panel.getByRole('region',{name:'Схема с прокруткой'}).evaluate(el=>el.scrollLeft+el.scrollTop)).toBe(0);
  expect(new URL(page.url()).searchParams.get('day')).toBe('2026-09-29');
});
}

test('compact schematic fills the viewport and closes with Escape',async({page})=>{
  await page.setViewportSize({width:1366,height:900});
  await page.goto('/?object=kns54an#network');
  const panel=page.getByRole('region',{name:'Схема водоводов',exact:true});
  await expect(panel.locator('[data-kind=pipe]').first()).toBeVisible();
  expect(await panel.locator('.pipeline-schematic-node rect').first().getAttribute('width')).toBe('160');
  const expand=panel.getByRole('button',{name:'На весь экран',exact:true});
  await expand.click();
  const dialog=page.getByRole('dialog',{name:'Схема водоводов на весь экран'});
  await expect(dialog).toBeVisible();
  const box=(await dialog.boundingBox())!;
  expect(box.x).toBe(0);expect(box.y).toBe(0);
  expect(box.width).toBe(1366);expect(box.height).toBe(900);
  expect((await dialog.getByRole('region',{name:'Схема с прокруткой'}).boundingBox())!.height).toBeGreaterThan(600);
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(expand).toBeFocused();
  await page.setViewportSize({width:390,height:844});
  await expand.click();
  await expect(dialog).toBeVisible();
  expect((await dialog.boundingBox())!.width).toBe(390);
  await dialog.getByRole('button',{name:'Свернуть',exact:true}).click();
  await expect(dialog).not.toBeVisible();
});
