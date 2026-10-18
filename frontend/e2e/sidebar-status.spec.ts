import { test, expect } from "@playwright/test";
import {goToSection} from "./helpers";

test("history exposes working analysis controls without selecting a snapshot", async ({page}) => {
  await page.goto("/?object=demo-ppd#timeline");
  await expect(page.getByRole("heading",{name:"Последние показатели",exact:true})).toBeVisible();
  await expect(page.getByText("ПАРАМЕТРЫ АНАЛИЗА",{exact:true})).toBeVisible();
  const aggregate = page.getByLabel("Агрегат",{exact:true});
  await expect(aggregate).toBeEnabled();
  await expect(aggregate).toHaveValue("");
  await aggregate.selectOption("НА-1");
  await expect.poll(() => new URL(page.url()).searchParams.get("aggregate")).toBe("НА-1");
  await expect(page.getByLabel("Граница показателей")).toHaveText("НА-1");
});

test("ready data and demo do not show redundant banners", async ({page}) => {
  await page.goto("/?object=demo-ppd#overview");
  await expect(page.getByRole("heading",{name:"Показатели станции",exact:true})).toBeVisible();
  await expect(page.getByText("Данные пригодны для расчёта",{exact:true})).toHaveCount(0);
  await expect(page.getByText("Демо: все режимы, оборудование и потери синтетические. Это учебный объект, а не производственные данные.",{exact:true})).toHaveCount(0);
  await goToSection(page, "forecast");
  await expect(page.getByText("Данные пригодны для расчёта",{exact:true})).toHaveCount(0);
});
