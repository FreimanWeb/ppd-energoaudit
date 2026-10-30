import { test, expect } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:5191" });
test("configured login gate rejects wrong password and logout removes API access", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await expect(page.getByLabel("Пароль", { exact: true })).toBeVisible();
  expect((await request.get("/api/objects")).status()).toBe(401);
  await page.getByLabel("Пароль", { exact: true }).fill("incorrect");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByLabel("Пароль", { exact: true }).fill("e2e-known-password");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Состояние объектов", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Состояние объектов", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Выйти", exact: true }).click();
  await expect(page.getByLabel("Пароль", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(async () => (await fetch("/api/objects")).status),
  ).toBe(401);
});
