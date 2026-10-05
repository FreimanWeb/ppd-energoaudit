export const pages = [
  { id: "overview", label: "Обзор", icon: "overview" },
  { id: "snapshot", label: "Режимный расчёт", icon: "overview" },
  { id: "telemetry", label: "Телеметрия", icon: "losses" },
  { id: "forecast", label: "Прогноз закачки", icon: "losses" },
  { id: "crm", label: "Прогноз CRM", icon: "scheme" },
  { id: "crm-wells", label: "Прогноз по скважинам", icon: "scheme" },
  { id: "scheme", label: "Схема ППД", icon: "scheme" },
  { id: "losses", label: "Карта потерь", icon: "losses" },
  { id: "working-point", label: "Рабочая точка", icon: "losses" },
  { id: "measures", label: "Мероприятия", icon: "losses" },
  { id: "onboarding", label: "Подключение объекта", icon: "sources" },
  { id: "formulas", label: "Формулы", icon: "sources" },
  { id: "sources", label: "Источники данных", icon: "sources" },
];
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
/** @param {import('./types').Plant[]} objects @param {string[]} waters @param {string[]} ngdus */
export function filterObjects(objects, waters, ngdus) {
  const result = objects.filter(
    (o) =>
      (!waters.length || waters.includes(o.water_type)) &&
      (!ngdus.length || ngdus.includes(o.ngdu_name)),
  );
  // Как в Streamlit: пустой результат фильтра возвращает полный каталог.
  return result.length ? result : objects;
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
