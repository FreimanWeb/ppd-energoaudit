import { test, expect } from "@playwright/test";

const screen = "/?object=kns54an&aggregate=" + encodeURIComponent("НА-2") + "&day=2026-09-28&timestamp=2026-09-28T12:00:00&mode=analysis#working-point";
const explanation = "Пояснение: Рабочая точка: насос × трубопровод";

test("explanations open on focus and hover, Escape dismisses without moving focus", async ({ page }) => {
  let release!: () => void;
  const dataReady = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/working-point", async route => {
    const response = await route.fetch();
    await dataReady;
    await route.fulfill({ response });
  });
  await page.goto(screen);
  await expect(page.getByLabel("Агрегат", { exact: true })).toHaveValue("НА-2");
  await expect(page.getByLabel("Момент измерения").locator("option:checked")).toBeEnabled();
  const button = page.getByRole("button", { name: explanation, exact: true });
  await button.focus();
  const tooltip = page.getByRole("tooltip");
  try {
    await expect(tooltip).toBeVisible();
    await expect(tooltip).toContainText("Фактическая точка");
  } finally {
    release();
  }
  await expect(page.getByRole("group", { name: "Характеристика Q–H", exact: true })).toBeVisible();
  await expect(tooltip).toBeVisible();
  await expect(button).toBeFocused();
  await expect(button).toHaveAttribute("aria-describedby", await tooltip.getAttribute("id") as string);
  await page.keyboard.press("Escape");
  await expect(tooltip).toHaveCount(0);
  await expect(button).toBeFocused();
  await page.locator("h1").first().click();
  await button.hover();
  await expect(tooltip).toBeVisible();
  await tooltip.hover();
  await expect(tooltip).toBeVisible();
  expect(await tooltip.evaluate(el => el.parentElement === document.body)).toBe(true);
});

test.describe("touch explanations", () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 700 } });
  test("tap toggles explanation; outside tap closes it and placement stays in viewport", async ({ page }) => {
    await page.goto(screen);
    await expect(page.getByLabel("Агрегат", { exact: true })).toHaveValue("НА-2");
    await expect(page.getByLabel("Момент измерения").locator("option:checked")).toBeEnabled();
    const button = page.getByRole("button", { name: explanation, exact: true });
    await button.tap();
    const tooltip = page.getByRole("tooltip");
    await expect(tooltip).toBeVisible();
    const rect = await tooltip.boundingBox();
    expect(rect!.x).toBeGreaterThanOrEqual(0);
    expect(rect!.x + rect!.width).toBeLessThanOrEqual(390);
    expect(rect!.y).toBeGreaterThanOrEqual(0);
    await button.tap();
    await expect(tooltip).toHaveCount(0);
    await button.tap();
    await expect(tooltip).toBeVisible();
    await page.locator("h1").first().tap();
    await expect(tooltip).toHaveCount(0);
  });
});

test("compact explanation animates both directions and leaves the accessibility tree on dismissal", async ({ page }) => {
  await page.goto(screen);
  await expect(page.getByRole("group", { name: "Характеристика Q–H", exact: true })).toBeVisible();
  const button = page.getByRole("button", { name: explanation, exact: true });
  await button.focus();
  const tooltip = page.getByRole("tooltip");
  await expect(tooltip).toBeVisible();
  const opening = await tooltip.evaluate(el => ({
    width: el.getBoundingClientRect().width,
    fontSize: getComputedStyle(el).fontSize,
    padding: parseFloat(getComputedStyle(el).paddingLeft),
    durations: el.getAnimations().map(animation => animation.effect?.getTiming().duration),
  }));
  expect(opening.width).toBeLessThanOrEqual(300);
  expect(opening.fontSize).toBe("12px");
  expect(opening.padding).toBeLessThanOrEqual(12);
  expect(opening.durations).toContain(140);
  await tooltip.evaluate(el => Promise.all(el.getAnimations().map(animation => animation.finished)));
  const closing = await page.evaluate(async () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await new Promise(requestAnimationFrame);
    await new Promise(requestAnimationFrame);
    const el = document.querySelector(".explanation-tooltip")!;
    return {
      state: el?.getAttribute("data-state"),
      hidden: el?.getAttribute("aria-hidden"),
      opacity: el ? parseFloat(getComputedStyle(el).opacity) : 0,
      duration: el ? getComputedStyle(el).animationDuration : "0s",
      durations: el?.getAnimations().map(animation => animation.effect?.getTiming().duration) ?? [],
    };
  });
  expect(closing.state).toBe("closing");
  expect(closing.hidden).toBe("true");
  expect(closing.duration).toContain("0.14s");
  expect(closing.opacity).toBeGreaterThan(0);
  expect(closing.opacity).toBeLessThan(1);
  expect(closing.durations).toContain(140);
  await expect(tooltip).toHaveCount(0);
  await expect(button).not.toHaveAttribute("aria-describedby", /.+/);
  await expect(button).toBeFocused();
  await expect(page.locator(".explanation-tooltip")).toHaveCount(0);
});

test("reduced motion disables tooltip animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(screen);
  await expect(page.getByRole("group", { name: "Характеристика Q–H", exact: true })).toBeVisible();
  await page.getByRole("button", { name: explanation, exact: true }).focus();
  const tooltip = page.getByRole("tooltip");
  await expect(tooltip).toBeVisible();
  expect(await tooltip.evaluate(el => el.getAnimations().length)).toBe(0);
  expect(await tooltip.evaluate(el => getComputedStyle(el).transitionDuration)).toBe("0s");
});
