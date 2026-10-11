export const navigationSections = [
  {
    label: "Состояние системы",
    pages: [
      { id: "overview", label: "Обзор", icon: "overview" },
      { id: "snapshot", label: "Режимный расчёт", icon: "snapshot" },
      { id: "telemetry", label: "Телеметрия", icon: "telemetry" },
    ],
  },
  {
    label: "Энергоэффективность",
    pages: [
      { id: "losses", label: "Карта потерь", icon: "losses" },
      { id: "working-point", label: "Рабочая точка", icon: "working-point" },
      { id: "measures", label: "Мероприятия", icon: "measures" },
    ],
  },
  {
    label: "Прогнозирование",
    pages: [
      { id: "forecast", label: "Прогноз закачки", icon: "forecast" },
      { id: "crm", label: "Прогноз CRM", icon: "crm" },
      { id: "crm-wells", label: "Прогноз по скважинам", icon: "crm-wells" },
    ],
  },
  {
    label: "Данные и методика",
    pages: [
      { id: "sources", label: "Источники данных", icon: "sources" },
      { id: "formulas", label: "Формулы", icon: "formulas" },
      { id: "onboarding", label: "Готовность данных", icon: "onboarding" },
    ],
  },
];
export const pages = navigationSections.flatMap(section => section.pages);
const fieldPages = new Set([
  "overview",
  "losses",
  "working-point",
  "measures",
  "formulas",
  "sources",
]);
/** @param {string} mode @param {string} page */
export function pageForMode(mode, page) {
  if (mode === "telemetry_view") return "telemetry";
  if (mode === "field_trip") return fieldPages.has(page) ? page : "overview";
  return pages.some((p) => p.id === page) ? page : "overview";
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
    mode: ["analysis", "field_trip", "telemetry_view"].includes(mode) ? mode : "analysis",
  };
}
/** @param {string} href @param {ReturnType<typeof readAnalysisContext>} context */
export function analysisContextURL(href, context) {
  const url = new URL(href);
  for (const [key, value] of Object.entries(context)) {
    const relevant = key !== "day" || context.mode !== "field_trip";
    const measured = key !== "timestamp" || context.mode === "analysis";
    if (value && relevant && measured) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  return url.href;
}
