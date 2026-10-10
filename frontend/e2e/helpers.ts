import { expect, type Page } from '@playwright/test';

export async function selectDate(page: Page, day: string) {
  const trigger = page.getByRole('button', { name: 'Дата', exact: true });
  await expect(trigger).toBeEnabled();
  await trigger.click();
  await page.getByLabel('Месяц календаря').fill(day.slice(0, 7));
  await page.getByRole('dialog', { name: 'Выбор даты' }).getByRole('button', { name: new RegExp(`^${day}:`) }).click();
  await expect(trigger).toHaveAttribute('data-date', day);
}
