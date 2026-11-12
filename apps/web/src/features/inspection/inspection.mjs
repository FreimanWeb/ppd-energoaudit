const flow = ["q_fact", "q_day", "t"];
const power = ["p_electric", "w", "t"];
const pressure = ["p_in", "p_out"];
/** @type {Record<string, {title:string, sources:string[], formulas:string[], loss?:string, addresses?:string[], stage?:string, chain?:string[], operatorField?:"bg_kw"|"output_kw"}>} */
export const inspections = {
  hall: {title: "Машинный блок по оборудованию", sources: [...pressure, ...flow, ...power], formulas: [], stage: "hall"},
  hall_causal: {title: "Причинное разложение машинного блока", sources: [...pressure, ...flow, ...power], formulas: [], stage: "hall"},
  efficiency_causes: {title: "Составляющие отклонения КПД", sources: [...pressure, ...flow, ...power], formulas: [], stage: "hall"},
  annual_losses: {title: "Годовая оценка потерь", sources: [...pressure, ...flow, ...power, "t_year"], formulas: ["44", "45"]},
  sec_fact: { title: "УРЭ факт", sources: ["w", "q_day"], formulas: ["16"] },
  sec_regime: { title: "УРЭ по режиму", sources: [...flow, ...power], formulas: [] },
  sec_calc: { title: "УРЭ расчётный", sources: pressure, formulas: ["14", "17"] },
  sec_optimal: { title: "УРЭ оптимальный", sources: ["p_in", "p_bg"], formulas: [], loss: "Дросселирование", addresses: ["45"] },
  eta_unit: { title: "КПД агрегата", sources: [...pressure, ...flow, ...power], formulas: ["11", "13"], loss: "Потери КПД", addresses: ["44"] },
  eta_nom: { title: "КПД номинальный", sources: [], formulas: ["14"] },
  load_factor: { title: "Коэффициент загрузки ЭД", sources: power, formulas: ["24"], loss: "Завышенная мощность ЭД", addresses: ["41"] },
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
  efficiency_loss: { title: "Потери по КПД", sources: [...pressure, ...flow, ...power, "t_year"], formulas: ["14", "17", "44"], loss: "Потери КПД", addresses: ["44"] },
  throttle_loss: { title: "Потери дросселирования", sources: ["p_out", "p_bg", ...flow, ...power, "t_year"], formulas: ["45"], loss: "Дросселирование", addresses: ["45"] },
  pump_bg_loss: { title: "Потери на участке насос–БГ", sources: ["p_out", "p_bg", ...flow, "t_year"], formulas: ["45"], loss: "Потери на участке Насос–БГ", addresses: ["45"] },
  hydraulic_bg_loss: { title: "Гидравлические потери насос–БГ", sources: ["p_out", "p_bg", ...flow], formulas: [], loss: "Гидравл. насос→БГ", addresses: ["45"], stage: "hall", chain: ["Гидравлика насос→БГ"] },
  nominal_loss: { title: "Потери при номинальном КПД", sources: [], formulas: ["14"], loss: "Номинальные" },
  useful_power: { title: "Полезная гидравлическая мощность", sources: [...pressure, ...flow], formulas: ["11"], loss: "Полезная мощность", stage: "hall", chain: ["Гидравлическая мощность на БГ"], operatorField: "bg_kw" },
  useful_output: { title: "Полезная мощность закачки", sources: [...flow, "rho"], formulas: [], stage: "wells", chain: ["Полезная закачка"] },
  wellhead_power: { title: "Гидравлическая мощность на устьях скважин", sources: [...flow, "rho"], formulas: [], stage: "wells", chain: ["Гидравлическая мощность на устьях"], operatorField: "output_kw" },
  suboptimal_loss: { title: "Неоптимальная подача", sources: flow, formulas: ["29", "30"], loss: "Неоптимальная подача", addresses: ["39"] },
  wear_loss: { title: "Износ", sources: [...pressure, ...flow, ...power], formulas: ["27", "30"], loss: "Износ", addresses: ["42"] },
  motor_loss: { title: "Завышенная мощность ЭД", sources: power, formulas: ["24", "25-26"], loss: "Завышенная мощность ЭД", addresses: ["41"] },
  viscosity_loss: { title: "Потери на вязкость", sources: ["rho", ...flow, ...power], formulas: ["30"], loss: "Вязкость", stage: "hall" },
  vfd_loss: { title: "Потери в преобразователе частоты", sources: ["p_electric"], formulas: [], stage: "hall", chain: ["Потери ПЧ"] },
  motor_chain_loss: { title: "Потери в электродвигателе", sources: power, formulas: ["24", "25-26"], stage: "hall", chain: ["Потери ЭД"] },
  transmission_loss: { title: "Потери в передаче", sources: [], formulas: [], stage: "hall", chain: ["Потери передачи"] },
  pump_loss: { title: "Потери в насосе", sources: [...pressure, ...flow, ...power], formulas: ["11", "27"], stage: "hall", chain: ["Потери насоса"] },
  pipes_loss: { title: "Потери в трубопроводах до скважин", sources: [...flow, "rho"], formulas: [], stage: "pipes", chain: ["Трение в трубопроводах", "Арматура сети и скважин"] },
  friction_loss: { title: "Трение в трубопроводах", sources: [...flow, "rho"], formulas: [], stage: "pipes", chain: ["Трение в трубопроводах"] },
  local_loss: { title: "Местные сопротивления сети и арматуры", sources: [...flow, "rho"], formulas: [], stage: "pipes", chain: ["Арматура сети и скважин"] },
  bore_loss: { title: "Трение в стволах скважин", sources: [...flow, "rho"], formulas: [], stage: "wells", chain: ["Трение в стволах скважин"] },
  choke_loss: { title: "Штуцирование нагнетательных скважин", sources: [...flow], formulas: [], stage: "pipes", chain: ["Штуцирование скважин", "Штуцирование нагнетательных скважин"] },
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
  if (page === "measures") { url.searchParams.delete("measure"); url.searchParams.delete("stage"); }
  url.hash = page === "losses" ? "machine-losses" : page;
  return url.href;
}
/** @param {string} key @param {"equipment"|"causal"} decomposition @param {string} [href] */
export function hallReportHref(key = "hall", decomposition = "equipment", href = location.href) {
  const url = new URL(inspectionHref("formulas", key, href));
  if (decomposition === "causal") url.searchParams.set("decomposition", "causal");
  else url.searchParams.delete("decomposition");
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
/** Стабильные идентификаторы: необработанное имя составляющей из API → ключ разбора. */
const lossInspectionKeys = {
  "Полезная мощность": "useful_power",
  "Полезная закачка": "useful_output",
  "Гидравлическая мощность на БГ": "useful_power",
  "Гидравлическая мощность на устьях": "wellhead_power",
  "Номинальные": "nominal_loss",
  "Номинальные потери НА": "nominal_loss",
  "Потери КПД": "efficiency_loss",
  "Потери из-за снижения КПД": "efficiency_loss",
  "Отклонение от номинального КПД": "efficiency_loss",
  "Износ": "wear_loss",
  "Неоптимальная подача": "suboptimal_loss",
  "Завышенная мощность ЭД": "motor_loss",
  "Вязкость": "viscosity_loss",
  "Дросселирование": "throttle_loss",
  "Потери на участке Насос–БГ": "pump_bg_loss",
  "Гидравл. насос→БГ": "hydraulic_bg_loss",
  "Гидравлика насос→БГ": "hydraulic_bg_loss",
  "Потери ПЧ": "vfd_loss",
  "Потери ЭД": "motor_chain_loss",
  "Потери передачи": "transmission_loss",
  "Потери насоса": "pump_loss",
  "Потери в трубопроводах": "pipes_loss",
  "Трение в трубопроводах": "friction_loss",
  "Арматура сети и скважин": "local_loss",
  "Трение в стволах скважин": "bore_loss",
  "Штуцирование скважин": "choke_loss",
  "Штуцирование нагнетательных скважин": "choke_loss",
};
/** @param {string|undefined} name */
export function lossInspectionKey(name) {
  return name != null && Object.hasOwn(lossInspectionKeys, name) ? lossInspectionKeys[name] : undefined;
}
/** @param {string|undefined} key @param {any} data */
export function chainInspectionItems(key, data) {
  const inspection = inspectionFor(key);
  if (!inspection?.chain?.length || data?.status !== "scenario") return [];
  if (inspection.operatorField) {
    const balance = data.operator_balance;
    if (balance?.boundary !== "wellhead_after_choke") return [];
    const power = balance[inspection.operatorField];
    if (typeof power !== "number" || !Number.isFinite(power)) return [];
    return [{
      name: inspection.title, power_kw: power, category: "полезная", provenance: "calculated",
      basis: inspection.operatorField === "output_kw"
        ? "Баланс до устьев после штуцеров; трение в стволах за этой границей. Сценарная оценка, не потеря."
        : "Гидравлическая мощность на БГ после потерь насос–БГ. Сценарная оценка, не потеря.",
    }];
  }
  return inspection.chain.flatMap(name => {
    const item = data.items?.find(entry => entry.name === name);
    return item ? [item] : [];
  });
}
/** Страница, на которой составляющая адресуется естественным образом. */
const lossStagePages = { hall: "machine-losses", pipes: "pipelines", wells: "wells" };
/** @param {string|undefined} key */
export function lossPage(key) {
  return lossStagePages[inspectionFor(key)?.stage ?? ""] ?? "machine-losses";
}
/** @param {string} key @param {string} [href] */
export function lossHref(key, href = location.href) {
  const url = new URL(href);
  if (!inspectionFor(key)) return url.href;
  url.searchParams.set("inspect", key);
  url.hash = lossPage(key);
  return url.href;
}
/** @template {{addresses?:string}} T @param {T[]} rows @param {string|undefined} key */
export function relatedMeasures(rows, key) {
  const addresses = inspectionFor(key)?.addresses ?? [];
  return rows.filter(row => addresses.some(id => String(row.addresses ?? "").includes(`(${id})`)));
}
/** @param {string|undefined} key @param {import("../../shared/types").Audit} audit */
export function sourceKeys(key, audit) {
  const keys = inspectionFor(key)?.sources ?? [];
  const daily = key === "sec_fact" && audit.scope.daily_kpi_is_fact;
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
  "УРЭ факт": "sec_fact", "УРЭ по режиму": "sec_regime", "УРЭ расчётный": "sec_calc", "УРЭ оптимальный": "sec_optimal",
  "КПД агрегата": "eta_unit", "КПД на выбранный момент": "eta_unit", "КПД номинальный": "eta_nom",
  "Коэффициент загрузки ЭД": "load_factor", "КПД ЭД расчётный": "eta_motor_real", "КПД насоса расчётный": "eta_pump",
  "Фактический напор": "h_fact", "Напор факт": "h_fact", "Должный напор": "h_due", "Подача": "flow",
  "Гидравлическая мощность": "hydraulic_power", "Электрическая мощность": "electric_power",
  "Давление на приёме": "p_in", "Давление на выкиде": "p_out", "Давление БГ": "p_bg",
};
