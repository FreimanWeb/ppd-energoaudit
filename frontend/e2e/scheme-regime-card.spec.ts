import { test, expect } from '@playwright/test';

test('pump regime remains readable, avoids equipment, and follows the active aggregate', async ({ page }) => {
  await page.setViewportSize({ width: 1800, height: 1000 });
  const response = page.waitForResponse(response => response.url().endsWith('/field-trip-audit'));
  await page.goto('/?object=kns54an&aggregate=НА-1&mode=field_trip#overview');
  const first = await (await response).json();
  const card = page.getByRole('group', { name: 'Режим выбранного агрегата', exact: true });
  const expectedValues = (audit: typeof first) => [
    audit.audit.metrics.h_fact_m, audit.audit.metrics.flow_m3h,
    audit.audit.metrics.p_electric_kw, audit.audit.metrics.p_hydraulic_kw,
  ].map(value => new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value));
  await expect(card.locator('strong')).toHaveText(expectedValues(first));
  await expect(card.locator('dt')).toHaveText(['Напор', 'Подача', 'Электрическая мощность', 'Гидравлическая мощность']);
  const font = await card.locator('strong').first().evaluate(node => getComputedStyle(node).fontSize);
  const svgHeight = await page.locator('.equipment-scheme').evaluate(node => node.getBoundingClientRect().height);
  const checkLeader = async () => {
    const geometry = await page.evaluate(() => {
      const leader = document.querySelector<SVGPathElement>('.pump-regime-leader path');
      if (!leader) return { crossesPipe: false, length: 0 };
      const pipes = [...document.querySelectorAll<SVGPathElement>('.equipment-scheme g[data-from] > path')];
      const length = leader.getTotalLength();
      const matrix = leader.getScreenCTM()!;
      for (let distance = 0; distance <= length; distance++) {
        const point = leader.getPointAtLength(distance);
        const screen = new DOMPoint(point.x, point.y).matrixTransform(matrix);
        if (pipes.some(pipe => pipe.isPointInStroke(screen.matrixTransform(pipe.getScreenCTM()!.inverse()))))
          return { crossesPipe: true, length };
      }
      return { crossesPipe: false, length };
    });
    expect(geometry.crossesPipe).toBe(false);
    expect(geometry.length).toBeLessThan(120);
  };

  for (const width of [1800, 1280, 1150, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect.poll(() => card.evaluate(node => {
      const bounds = node.getBoundingClientRect();
      return [...document.querySelectorAll('.equipment-node use')].filter(symbol => {
        const box = symbol.getBoundingClientRect();
        return bounds.left < box.right && bounds.right > box.left && bounds.top < box.bottom && bounds.bottom > box.top;
      }).length;
    })).toBe(0);
    expect(await card.locator('strong').first().evaluate(node => getComputedStyle(node).fontSize)).toBe(font);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await checkLeader();
    const positions = await card.locator('dl > div').evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect()));
    expect(positions[0].y).toBeCloseTo(positions[1].y, 1);
    expect(positions[2].y).toBeCloseTo(positions[3].y, 1);
    expect(positions[2].y).toBeGreaterThan(positions[0].y);
  }

  await page.setViewportSize({ width: 1800, height: 1000 });
  const secondResponse = page.waitForResponse(response => response.url().includes(encodeURIComponent('НА-2')) && response.url().endsWith('/field-trip-audit'));
  await page.getByLabel('Агрегат', { exact: true }).selectOption('НА-2');
  const second = await (await secondResponse).json();
  await expect(card.getByRole('heading')).toHaveText('НА-2 · параметры режима');
  await expect(card.locator('strong')).toHaveText(expectedValues(second));
  await expect.poll(() => page.locator('.pump-regime-leader circle').evaluate(circle => {
    const dot = circle.getBoundingClientRect();
    const pump = document.querySelector('.equipment-node[aria-pressed="true"] .node-hit')!.getBoundingClientRect();
    const x = dot.x + dot.width / 2, y = dot.y + dot.height / 2;
    return x >= pump.left && x <= pump.right && y >= pump.top && y <= pump.bottom;
  })).toBe(true);
  await checkLeader();
  expect(await page.locator('.equipment-scheme').evaluate(node => node.getBoundingClientRect().height)).toBe(svgHeight);
});
