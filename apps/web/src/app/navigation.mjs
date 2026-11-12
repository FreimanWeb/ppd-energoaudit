export const navigationSections = [
  {label:"Все объекты",root:"portfolio",pages:[
    {id:"portfolio",label:"Все объекты",icon:"portfolio"},
  ]},
  {label:"Обзор",root:"timeline",pages:[
    {id:"timeline",label:"История показателей",icon:"timeline"},
    {id:"overview",label:"Схема и участки",icon:"overview"},
    {id:"losses",label:"Карта потерь",icon:"losses"},
    {id:"loss-detail",label:"Составляющая потерь",icon:"loss-detail",hidden:true},
  ]},
  {label:"Машинный блок",root:"machine-block",pages:[
    {id:"machine-block",label:"Показатели",icon:"machine-block"},
    {id:"machine-losses",label:"Карта потерь",icon:"machine-losses"},
    {id:"working-point",label:"Рабочая точка",icon:"working-point"},
    {id:"recommendations",label:"Рекомендации",icon:"recommendations"},
  ]},
  {label:"Трубопроводы",root:"pipelines",pages:[
    {id:"pipelines",label:"Потери",icon:"pipelines"},
    {id:"network",label:"Разводящая сеть",icon:"network"},
    {id:"network-scenario",label:"Гидравлический сценарий",icon:"scheme"},
  ]},
  {label:"Скважины",root:"wells",pages:[
    {id:"wells",label:"Потери",icon:"wells"},
    {id:"forecast",label:"Прогноз закачки НА",icon:"forecast"},
    {id:"well-history",label:"История и ГДИ",icon:"telemetry"},
    {id:"crm",label:"Прогноз по агрегатам",icon:"crm",hidden:true},
    {id:"crm-wells",label:"Прогноз по скважинам · CRM",icon:"crm-wells"},
  ]},
  {label:"Мероприятия",root:"measures",pages:[
    {id:"measures",label:"Мероприятия",icon:"measures"},
  ]},
  {label:"Данные и методика",root:"sources",pages:[
    {id:"sources",label:"Источники",icon:"sources"},
    {id:"telemetry",label:"Телеметрия",icon:"telemetry-data"},
    {id:"snapshot",label:"Режимный расчёт",icon:"snapshot"},
    {id:"formulas",label:"Формулы",icon:"formulas"},
    {id:"equipment-journal",label:"Журнал оборудования",icon:"sources"},
    {id:"reference",label:"Справочник",icon:"reference"},
    {id:"onboarding",label:"Готовность данных",icon:"onboarding"},
  ]},
];
export const pages = navigationSections.flatMap(section => section.pages);
const fieldPages = new Set([
  "overview",
  "machine-block",
  "machine-losses",
  "pipelines",
  "wells",
  "well-history",
  "losses",
  "loss-detail",
  "recommendations",
  "reference",
  "network-scenario",
  "network",
  "equipment-journal",
  "onboarding",
  "working-point",
  "measures",
  "formulas",
  "sources",
  "snapshot",
]);
/** @param {string} mode @param {string} page */
export function pageForMode(mode, page) {
  if (page === "portfolio") return page;
  if (mode === "telemetry_view") return "telemetry";
  if (mode === "field_trip") return fieldPages.has(page) ? page : "overview";
  return pages.some((p) => p.id === page) ? page : "overview";
}

/** @param {string} href */
export function initialPage(href) {
  const url = new URL(href);
  if (url.hash) return url.hash.slice(1);
  const context = readAnalysisContext(href);
  if (context.mode === "field_trip") return "overview";
  if (context.mode === "telemetry_view") return "telemetry";
  return context.object ? "timeline" : "portfolio";
}
/** @param {import('../shared/types').Plant[]} objects @param {string[]} waters @param {string[]} ngdus */
export function filterObjects(objects, waters, ngdus) {
  const result = objects.filter(
    (o) =>
      (!waters.length || waters.includes(o.water_type)) &&
      (!ngdus.length || ngdus.includes(o.ngdu_name)),
  );
  return result;
}
/** @param {string} month */
export function monthDays(month) {
  const [year, number] = month.split("-").map(Number);
  const first = new Date(Date.UTC(year, number - 1, 1)),
    last = new Date(Date.UTC(year, number, 0));
  const blank = (first.getUTCDay() + 6) % 7;
  const result = Array(blank).fill(null);
  for (let day = 1; day <= last.getUTCDate(); day++)
    result.push(`${month}-${String(day).padStart(2, "0")}`);
  while (result.length % 7) result.push(null);
  return result;
}


/** @param {string} href */
export function readAnalysisContext(href) {
  const params = new URL(href).searchParams;
  const mode = params.get("mode") ?? "analysis";
  return {
    object: params.get("object") ?? "",
    aggregate: params.get("aggregate") ?? "",
    day: params.get("day") ?? "",
    timestamp: params.get("timestamp") ?? "",
    measurement: params.get("measurement") ?? "",
    mode: ["analysis", "field_trip", "telemetry_view"].includes(mode) ? mode : "analysis",
  };
}
/** @param {string} href @param {ReturnType<typeof readAnalysisContext>} context */
export function analysisContextURL(href, context) {
  const url = new URL(href);
  for (const [key, value] of Object.entries(context)) {
    const manual = key !== "measurement" || context.mode === "field_trip";
    if (!manual) { url.searchParams.delete(key); continue; }
    const relevant = key !== "day" || context.mode !== "field_trip";
    const measured = key !== "timestamp" || context.mode === "analysis";
    if (value && relevant && measured) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  return url.href;
}


/** @param {string} focus @param {string} [href] */
export function equipmentJournalHref(focus, href = location.href) {
  const url = new URL(href);
  url.searchParams.delete("return_to");
  url.searchParams.delete("focus");
  const back = `${url.pathname}${url.search}${url.hash}`;
  url.searchParams.set("return_to", back);
  url.searchParams.set("focus", focus);
  url.hash = "equipment-journal";
  return `${url.pathname}${url.search}${url.hash}`;
}

/** Возврат допустим только в тот же расчётный контекст приложения.
 * @param {string} [href] @returns {string|null} */
export function equipmentReturnHref(href = location.href) {
  const current = new URL(href);
  const destination = current.searchParams.get("return_to");
  if (!destination) return null;
  try {
    const target = new URL(destination, current);
    if (target.origin !== current.origin || target.pathname !== current.pathname ||
        target.hash === "#equipment-journal" || !pages.some(page => `#${page.id}` === target.hash)) return null;
    const context = readAnalysisContext(current.href), previous = readAnalysisContext(target.href);
    if (Object.keys(context).some(key => context[key] !== previous[key])) return null;
    target.searchParams.delete("return_to");
    target.searchParams.delete("focus");
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return null;
  }
}
