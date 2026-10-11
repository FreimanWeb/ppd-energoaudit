const flow = ["q_fact", "q_day", "t"];
const power = ["p_electric", "w", "t"];
const pressure = ["p_in", "p_out"];
/** @type {Record<string, {title:string, sources:string[], formulas:string[], loss?:string, addresses?:string[]}>} */
export const inspections = {
  sec_fact: { title: "УРЭ факт", sources: ["w", "q_day"], formulas: ["16"], loss: "Потери КПД", addresses: ["44"] },
  sec_calc: { title: "УРЭ расчётный", sources: pressure, formulas: ["14", "17"] },
  sec_optimal: { title: "УРЭ оптимальный", sources: ["p_in", "p_bg"], formulas: [], loss: "Дросселирование", addresses: ["45"] },
  eta_unit: { title: "КПД агрегата", sources: [...pressure, ...flow, ...power], formulas: ["11", "13"], loss: "Потери КПД", addresses: ["44"] },
  eta_nom: { title: "КПД номинальный", sources: [], formulas: ["14"] },
  load_factor: { title: "Коэффициент загрузки ЭД", sources: power, formulas: ["24"], loss: "Завыш. мощность ЭД", addresses: ["41"] },
  eta_motor_real: { title: "КПД ЭД расчётный", sources: power, formulas: ["24", "25-26"] },
  eta_pump: { title: "КПД насоса расчётный", sources: [...pressure, ...flow, ...power], formulas: ["13", "25-26", "27"], loss: "Износ", addresses: ["42"] },
  h_fact: { title: "Фактический напор", sources: [...pressure, "rho"], formulas: ["8"] },
  h_due: { title: "Должный напор", sources: flow, formulas: ["29"] },
  flow: { title: "Подача", sources: flow, formulas: [] },
  hydraulic_power: { title: "Гидравлическая мощность", sources: [...pressure, ...flow], formulas: ["11"] },
  electric_power: { title: "Электрическая мощность", sources: power, formulas: [] },
  p_in: { title: "Давление на приёме", sources: ["p_in"], formulas: ["8"] },
  p_out: { title: "Давление на выкиде", sources: ["p_out"], formulas: ["8"] },
  p_bg: { title: "Давление БГ", sources: ["p_bg"], formulas: [], loss: "Дросселирование", addresses: ["45"] },
  efficiency_loss: { title: "Потери по КПД", sources: [...pressure, ...flow, ...power, "t_year"], formulas: ["16", "17", "44"], loss: "Потери КПД", addresses: ["44"] },
  throttle_loss: { title: "Потери дросселирования", sources: ["p_out", "p_bg", ...flow, ...power, "t_year"], formulas: [], loss: "Дросселирование", addresses: ["45"] },
  suboptimal_loss: { title: "Неоптимальная подача", sources: flow, formulas: ["29", "30"], loss: "Неоптим. подача", addresses: ["39"] },
  wear_loss: { title: "Износ", sources: [...pressure, ...flow, ...power], formulas: ["27", "30"], loss: "Износ", addresses: ["42"] },
  motor_loss: { title: "Завышенная мощность ЭД", sources: power, formulas: ["24", "25-26"], loss: "Завыш. мощность ЭД", addresses: ["41"] },
};
/** @param {string|undefined} key */
export function inspectionFor(key) {
  return key != null && Object.hasOwn(inspections, key) ? inspections[key] : undefined;
}
/** @param {string} page @param {string|undefined} key @param {string} href */
export function inspectionHref(page, key, href = location.href) {
  const url = new URL(href);
  if (inspectionFor(key)) url.searchParams.set("inspect", key ?? "");
  else url.searchParams.delete("inspect");
  url.hash = page;
  return url.href;
}
/** @param {string|undefined} key @param {string} [href] */
export function metricLinks(key, href) {
  const item = inspectionFor(key);
  return item ? [
    ...(item.loss ? [{ label: "Потери", href: inspectionHref("losses", key, href) }] : []),
    { label: "Источники", href: inspectionHref("sources", key, href) },
    { label: "Формулы", href: inspectionHref("formulas", key, href) },
  ] : [];
}
/** @template {{addresses?:string}} T @param {T[]} rows @param {string|undefined} key */
export function relatedMeasures(rows, key) {
  const addresses = inspectionFor(key)?.addresses ?? [];
  return rows.filter(row => addresses.some(id => String(row.addresses ?? "").includes(`(${id})`)));
}
/** @param {string|undefined} key @param {import("../../shared/types").Audit} audit */
export function sourceKeys(key, audit) {
  let keys = inspectionFor(key)?.sources ?? [];
  if (key === "sec_fact" && !audit.scope.daily_kpi_is_fact) keys = [...flow, ...power];
  const daily = ["sec_fact", "efficiency_loss"].includes(key) && audit.scope.daily_kpi_is_fact;
  const used = new Set(keys);
  if (used.has("q_fact")) {
    if (audit.regime.q_fact == null) used.delete("q_fact");
    else if (!daily) used.delete("q_day");
  }
  if (used.has("p_electric") && audit.quality.basis.power !== "W_сут / T_сут" && !(audit.regime.p_electric == null && audit.regime.w != null && audit.regime.t)) {
    if (!daily) used.delete("w");
    if (!used.has("q_day")) used.delete("t");
  }
  return [...used];
}
/** @type {Record<string,string>} */
export const metricKeys = {
  "УРЭ факт": "sec_fact", "УРЭ расчётный": "sec_calc", "УРЭ оптимальный": "sec_optimal",
  "КПД агрегата": "eta_unit", "КПД на выбранный момент": "eta_unit", "КПД номинальный": "eta_nom",
  "Коэффициент загрузки ЭД": "load_factor", "КПД ЭД расчётный": "eta_motor_real", "КПД насоса расчётный": "eta_pump",
  "Фактический напор": "h_fact", "Напор факт": "h_fact", "Должный напор": "h_due", "Подача": "flow",
  "Гидравлическая мощность": "hydraulic_power", "Электрическая мощность": "electric_power",
  "Давление на приёме": "p_in", "Давление на выкиде": "p_out", "Давление БГ": "p_bg",
};
