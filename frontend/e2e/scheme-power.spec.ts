import {test,expect} from '@playwright/test';

const query='/?object=demo-ppd&day=2026-10-18&timestamp=2026-10-18T22:00:00#overview';

test('scheme shows neutral power readings above equipment with leaders',async({page})=>{
  await page.setViewportSize({width:1600,height:1100});
  const response=page.waitForResponse(r=>r.url().endsWith('/station-summary'));
  await page.goto(query);
  const data=await (await response).json();
  const balance=data.network.operator_balance;
  const scheme=page.getByRole('region',{name:'Условная технологическая схема ППД',exact:true});
  const readings=scheme.locator('svg.equipment-scheme .scheme-power-reading');
  await expect(readings).toHaveCount(3);
  const pipeColors=await scheme.locator(".equipment-scheme g[data-from] path").evaluateAll(paths=>paths.map(path=>getComputedStyle(path).stroke));
  expect(new Set(pipeColors).size).toBe(1);
  expect(await readings.locator(".scheme-power-label").evaluateAll(nodes=>nodes.map(node=>[...node.querySelectorAll("tspan")].map(span=>span.textContent).join(" ")))).toEqual(["Потреблённая мощность","Гидравлическая мощность на БГ","Полезная гидравлическая мощность на устьях скважин"]);
  for(const [id,power] of [['input',balance.input_kw],['bg',balance.bg_kw],['output',balance.output_kw]] as const){
    const reading=scheme.locator(`.scheme-power-reading[data-reading="${id}"]`);
    await expect(reading).toHaveAttribute('data-power',String(power));
    await expect(reading.locator('.scheme-power-value')).toContainText(`${new Intl.NumberFormat('ru-RU',{maximumFractionDigits:1}).format(power)} кВт`);
    await expect(reading.locator('.scheme-power-share')).toContainText(`${new Intl.NumberFormat('ru-RU',{maximumFractionDigits:1}).format(power/balance.input_kw*100)} % ввода`);
    const caption=(await reading.locator('.scheme-power-label').boundingBox())!;
    const value=(await reading.locator('.scheme-power-value').boundingBox())!;
    const share=(await reading.locator('.scheme-power-share').boundingBox())!;
    expect(caption.y+caption.height).toBeLessThan(value.y);
    expect(value.y+value.height).toBeLessThan(share.y);
    expect(Math.abs(caption.x+caption.width/2-value.x-value.width/2)).toBeLessThan(1);
    await expect(reading.locator('rect')).toHaveCount(0);
  }
  const input=(await scheme.locator('.scheme-power-reading[data-reading="input"] .scheme-power-share').boundingBox())!;
  const hall=(await scheme.locator('.scheme-area-link[data-stage="hall"] rect').boundingBox())!;
  expect(input.y+input.height).toBeLessThan(hall.y);
  const inputPoint=(await scheme.locator('.scheme-power-reading[data-reading="input"] circle').boundingBox())!;
  expect(Math.abs(inputPoint.x+inputPoint.width/2-hall.x)).toBeLessThan(1);
  expect(inputPoint.y).toBeGreaterThan(hall.y);
  const bgPoint=(await scheme.locator('.scheme-power-reading[data-reading="bg"] circle').boundingBox())!;
  const bg=(await scheme.locator('.equipment-node use[href="#ppd-manifold"]').boundingBox())!;
  expect(Math.abs(bgPoint.y+bgPoint.height/2-bg.y)).toBeLessThan(1);
  const output=scheme.locator('.scheme-power-reading[data-reading="output"]');
  expect(await output.locator('path').evaluate(element=>{
    const path=element as SVGPathElement,start=path.getPointAtLength(0),next=path.getPointAtLength(1);
    return start.x===0 && Math.abs(next.x-start.x)<.01 && next.y>start.y;
  })).toBe(true);

  await expect(readings.locator(".scheme-power-leader")).toHaveCount(3);
  for(const reading of await readings.all()){
    const share=(await reading.locator(".scheme-power-share").boundingBox())!;
    expect(share.y+share.height).toBeLessThan(hall.y);
    const connected=await reading.evaluate(element=>{
      const path=element.querySelector<SVGPathElement>("path")!,anchor=element.querySelector<SVGCircleElement>("circle")!;
      const end=path.getPointAtLength(path.getTotalLength());
      return Math.hypot(end.x-anchor.cx.baseVal.value,end.y-anchor.cy.baseVal.value)<1;
    });
    expect(connected).toBe(true);
  }
  await expect(scheme.getByText('Баланс мощности',{exact:true})).toHaveCount(0);
  await expect(scheme.locator('.loss-flow-article')).toHaveCount(6);
  const bounds=(await scheme.locator('svg.equipment-scheme').boundingBox())!;
  for(const reading of await readings.all()){
    const box=(await reading.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(bounds.y);
    expect(box.y+box.height).toBeLessThanOrEqual(bounds.y+bounds.height);
  }
});

test('unknown power does not turn into a fictitious 100 percent input',async({page})=>{
  const response=await page.request.post('/api/objects/demo-ppd/station-summary',{data:{source:'telemetry',day:'2026-10-18',timestamp:'2026-10-18T22:00:00'}});
  const data=await response.json();
  await page.route('**/station-summary',route=>route.fulfill({json:{...data,network:{status:'unavailable',warnings:[]}}}));
  await page.goto(query);
  const readings=page.locator('svg.equipment-scheme .scheme-power-value');
  await expect(readings).toHaveText(['Нет данных','Нет данных','Нет данных']);
  await page.unrouteAll({behavior:'wait'});
});


test('choke belongs to the BG-to-wellhead area while wells retain useful power',async({page})=>{
  await page.goto(query);
  const scheme=page.getByRole('region',{name:'Условная технологическая схема ППД',exact:true});
  const choke=scheme.locator('.equipment-node').filter({has:page.locator('use[href="#ppd-choke"]')});
  await expect(choke).toHaveCount(1);
  await expect(choke).toHaveAttribute('aria-label','Штуцеры нагнетательных скважин');
  const chokeId=await choke.getAttribute('data-node');
  await expect(scheme.locator(`g[data-to="${chokeId}"] > path`)).toHaveAttribute('stroke-dasharray','7 4');
  await expect(scheme.locator(`g[data-from="${chokeId}"] > path`)).not.toHaveAttribute('stroke-dasharray',/.+/);
  await expect(scheme.locator('.loss-flow-group[data-stage="wells"]')).toHaveCount(0);
  const symbol=(await choke.locator('use').boundingBox())!;
  const wellArea=(await scheme.locator('.scheme-area-link[data-stage="wells"] rect').boundingBox())!;
  const pipeArea=(await scheme.locator('.scheme-area-link[data-stage="pipes"] rect').boundingBox())!;
  expect(symbol.x+symbol.width).toBeLessThan(wellArea.x);
  expect(symbol.x).toBeGreaterThan(pipeArea.x);
  expect(symbol.x+symbol.width).toBeLessThan(pipeArea.x+pipeArea.width);
  expect(wellArea.x-pipeArea.x-pipeArea.width).toBeGreaterThan(5);
  const valve=scheme.locator('.equipment-node').filter({has:page.locator('use[href="#ppd-valve"]')});
  await expect(valve).toHaveCount(1);
  await expect(valve).toHaveAttribute('aria-label','ЗРА');
  const valveSymbol=(await valve.locator('use').boundingBox())!;
  expect(valveSymbol.x).toBeGreaterThan(pipeArea.x);
  expect(valveSymbol.x+valveSymbol.width).toBeLessThan(pipeArea.x+pipeArea.width);
  expect(valveSymbol.x+valveSymbol.width).toBeLessThan(symbol.x);
  await scheme.locator('.scheme-area-link[data-stage="pipes"]').hover();
  await expect(scheme.locator('.loss-flow-article[data-stage="pipes"]').first()).toHaveAttribute('data-active','true');
  await scheme.locator('.scheme-area-link[data-stage="wells"]').hover();
  await expect(scheme.locator('.loss-flow-article[data-stage="wells"]')).toHaveCount(0);
  await expect(scheme.locator('.scheme-power-reading[data-reading="output"]')).toBeVisible();
});
