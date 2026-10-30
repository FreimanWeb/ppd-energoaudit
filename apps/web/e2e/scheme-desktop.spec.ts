import {test,expect} from '@playwright/test';

for(const width of [1280,1440]) test(`station scheme fits ${width}px before estimates and retains an accessible enlarged view`,async({page})=>{
  await page.setViewportSize({width,height:900});
  await page.goto('/?object=demo-ppd#overview');
  const scheme=page.getByRole('region',{name:'Условная технологическая схема ППД',exact:true});
  await expect(scheme.locator('.loss-flow-article')).toHaveCount(6);
  const viewport=scheme.locator('.scheme-layout');
  await expect.poll(()=>viewport.evaluate(node=>node.scrollWidth-node.clientWidth)).toBeLessThanOrEqual(1);
  const annual=page.getByRole('heading',{name:/^Годовая оценка · сценарий/});
  expect((await scheme.boundingBox())!.y).toBeLessThan((await annual.boundingBox())!.y);
  expect(await scheme.locator('.loss-flow-article-label').first().evaluate(node=>parseFloat(getComputedStyle(node).fontSize))).toBeGreaterThanOrEqual(12);
  expect(await scheme.locator('.scheme-power-label').first().evaluate(node=>{
    const svg=node.closest<SVGSVGElement>('.equipment-scheme')!;
    return parseFloat(getComputedStyle(node).fontSize)*svg.getBoundingClientRect().width/svg.viewBox.baseVal.width;
  })).toBeGreaterThanOrEqual(11.9);
  const overlaps=await scheme.locator('.equipment-scheme').evaluate(svg=>{
    const labels=[...svg.querySelectorAll('.node-label,.node-sub,.hall-label,.scheme-power-label,.scheme-power-value,.scheme-power-share')].map(node=>node.getBoundingClientRect());
    return labels.some((a,i)=>labels.slice(i+1).some(b=>Math.min(a.right,b.right)-Math.max(a.left,b.left)>1 && Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1));
  });
  expect(overlaps).toBe(false);
  await scheme.getByRole('button',{name:'Крупнее',exact:true}).click();
  await expect(scheme.getByText('Крупная схема: прокручивайте по горизонтали или откройте на весь экран.')).toBeVisible();
  expect(await viewport.evaluate(node=>node.scrollWidth-node.clientWidth)).toBeGreaterThan(100);
  await scheme.getByRole('button',{name:'Вписать целиком',exact:true}).click();
  await expect.poll(()=>viewport.evaluate(node=>node.scrollWidth-node.clientWidth)).toBeLessThanOrEqual(1);
  const expand=scheme.getByRole('button',{name:'На весь экран',exact:true});
  await expand.click();
  const dialog=page.getByRole('dialog',{name:'Технологическая схема на весь экран'});
  await expect(dialog).toBeVisible();
  const box=(await dialog.boundingBox())!;
  expect(box.width).toBe(width);expect(box.height).toBe(900);
  await expect(dialog.locator('.loss-flow-article')).toHaveCount(6);
  const leaderError=await dialog.locator('.scheme-canvas').evaluate(element=>{
    const bounds=element.getBoundingClientRect();
    return [...element.querySelectorAll<SVGPathElement>('.scheme-leaders path')].some(path=>{
      const point=path.getPointAtLength(0);
      const card=element.querySelector(`[data-loss="${path.dataset.loss}"].loss-flow-article`)!.getBoundingClientRect();
      return Math.abs(point.x-(card.x+card.width/2-bounds.x))>1;
    });
  });
  expect(leaderError).toBe(false);
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(expand).toBeFocused();
  await expand.press('Enter');
  await dialog.getByRole('button',{name:'Свернуть',exact:true}).click();
  await expect(expand).toBeFocused();
});

for(const width of [1920,2560]) test(`scheme omits equivalent size modes at ${width}px and adapts to its container`,async({page})=>{
  await page.setViewportSize({width,height:1000});
  await page.goto('/?object=demo-ppd#overview');
  const scheme=page.getByRole('region',{name:'Условная технологическая схема ППД',exact:true});
  await expect(scheme.locator('.loss-flow-article')).toHaveCount(6);
  await expect(scheme.getByRole('button',{name:'Крупнее',exact:true})).toHaveCount(0);
  await expect(scheme.getByRole('button',{name:'Вписать целиком',exact:true})).toHaveCount(0);
  const expand=scheme.getByRole('button',{name:'На весь экран',exact:true});
  await expect(expand).toBeVisible();
  await scheme.evaluate(node=>node.style.width='1000px');
  await expect(scheme.getByRole('button',{name:'Крупнее',exact:true})).toBeVisible();
  await scheme.evaluate(node=>node.style.width='');
  await expect(scheme.getByRole('button',{name:'Крупнее',exact:true})).toHaveCount(0);
  await page.setViewportSize({width:1280,height:1000});
  const viewport=scheme.locator('.scheme-layout');
  const natural=scheme.locator('.scheme-canvas');
  await expect(scheme.getByRole('button',{name:'Крупнее',exact:true})).toBeVisible();
  const fitWidth=(await natural.boundingBox())!.width;
  await scheme.getByRole('button',{name:'Крупнее',exact:true}).click();
  expect((await natural.boundingBox())!.width).toBeGreaterThan(fitWidth+100);
  expect(await viewport.evaluate(node=>node.scrollWidth-node.clientWidth)).toBeGreaterThan(100);
  // The natural canvas stays 1400px while its parent changes width.
  await page.setViewportSize({width,height:1000});
  await expect(scheme.getByRole('button',{name:'Крупнее',exact:true})).toHaveCount(0);
  await expect(scheme.locator('.scheme-scroll-hint')).toHaveCount(0);
  await page.setViewportSize({width:1280,height:1000});
  await expect(scheme.getByRole('button',{name:'Крупнее',exact:true})).toBeVisible();
  await expand.click();
  const dialog=page.getByRole('dialog',{name:'Технологическая схема на весь экран'});
  await expect(dialog.getByRole('button',{name:'Крупнее',exact:true})).toBeVisible();
  await page.setViewportSize({width,height:1000});
  await expect(dialog.getByRole('button',{name:'Крупнее',exact:true})).toHaveCount(0);
  await expect(dialog.getByRole('button',{name:'Вписать целиком',exact:true})).toHaveCount(0);
  await dialog.getByRole('button',{name:'Свернуть',exact:true}).click();
  await expect(expand).toBeFocused();
});
