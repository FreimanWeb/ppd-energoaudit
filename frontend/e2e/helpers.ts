import { expect, type Page } from '@playwright/test';

export async function selectDate(page: Page, day: string, label = 'Дата') {
  const trigger = page.getByRole('button', { name: label, exact: true });
  await expect(trigger).toBeEnabled();
  await trigger.click();
  await page.getByLabel('Месяц календаря').fill(day.slice(0, 7));
  await page.getByRole('dialog', { name: 'Выбор даты' }).getByRole('button', { name: new RegExp(`^${day}(:|$)`) }).click();
  await expect(trigger).toHaveAttribute('data-date', day);
}


export async function goToSection(page: Page, target: string) {
  const {navigationSections} = await import('../src/app/navigation.mjs');
  const id = target === 'scheme' ? 'overview' : target;
  const group = navigationSections.find(section => section.pages.some(item => item.id === id))!;
  if(group.pages.find(item=>item.id===id)?.hidden) {
    const url=new URL(page.url());url.hash=id;await page.goto(url.href);return;
  }
  let tab = page.locator(`.page-tabs a[href$="#${id}"]`);
  if (await tab.count() === 0) {
    const root = page.locator(`.sidebar-nav a[href$="#${group.root}"]`);
    if (!await root.isVisible()) {
      const toggle = page.getByRole('button',{name:'Открыть боковую панель',exact:true});
      if (await toggle.count()) await toggle.click();
    }
    await root.click();
    if (id === group.root) return;
    tab = page.locator(`.page-tabs a[href$="#${id}"]`);
  }
  await tab.click();
}
