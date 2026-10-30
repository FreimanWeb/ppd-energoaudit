import {test, expect} from '@playwright/test';

test('stale historical comparisons stay unknown and out of current normal summary', async ({page}) => {
  await page.route('**/api/monitoring/objects?**', route => route.fulfill({json: {
    generated_at:'2026-10-25T20:00:00+03:00', interval_hours:2,
    objects:[
      {code:'kns54an',name:'Архивная КНС',ngdu_name:'НГДУ',water_type:'пресная',status:'unknown',comparison_status:'normal',data_status:'stale',latest_at:'2026-09-01T00:00:00',kpi_at:'2026-09-01T00:00:00',basis:'daily',sec_kwh_m3:3,efficiency:null,change_pct:2,history:[],note:'Текущее состояние неизвестно: нет актуального УРЭ.'},
      {code:'demo-ppd',name:'Актуальная КНС',ngdu_name:'НГДУ',water_type:'пресная',status:'normal',comparison_status:'normal',data_status:'fresh',latest_at:'2026-10-25T20:00:00',kpi_at:'2026-10-25T20:00:00',basis:'interval',sec_kwh_m3:3,efficiency:null,change_pct:2,history:[],note:''},
    ],
  }}));
  await page.goto('/');
  const old = page.locator('.portfolio-card').filter({has:page.getByRole('heading',{name:'Архивная КНС',exact:true})});
  await expect(old.locator('.portfolio-badge')).toHaveText('Текущее состояние неизвестно');
  await expect(old.locator('.portfolio-badge-normal')).toHaveCount(0);
  await expect(old).toContainText('Последнее сравнение в архиве');
  const summary = page.getByLabel('Сводка по объектам');
  await expect(summary.locator('div').filter({hasText:'Без скачка в последнем сравнении'}).locator('strong')).toHaveText('1');
  await expect(summary.locator('div').filter({hasText:'Текущее состояние неизвестно'}).locator('strong')).toHaveText('1');
  await page.getByRole('combobox',{name:/^Состояние/}).selectOption('normal');
  await expect(page.locator('.portfolio-card')).toHaveCount(1);
  await expect(page.locator('.portfolio-card')).toContainText('Актуальная КНС');
});

test('readiness checks the selected snapshot and names its basis', async ({page}) => {
  const requested:URL[] = [];
  page.on('request', request => {
    if (request.url().includes('/onboarding?')) requested.push(new URL(request.url()));
  });
  await page.goto('/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T22:00:00#onboarding');
  await expect(page.getByRole('heading',{name:/^Готовность данных/})).toBeVisible();
  await expect(page.getByLabel('База проверки данных')).toContainText('18.10.2026');
  await expect(page.getByLabel('База проверки данных')).toContainText('22:00');
  await expect(page.getByLabel('Недостающие базовые данные')).toHaveCount(0);
  expect(requested.at(-1)?.searchParams.get('timestamp')).toBe('2026-10-18T22:00:00');
});
