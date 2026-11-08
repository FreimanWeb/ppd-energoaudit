import dictionary from "../../../../../shared/loss-labels.json" with {type:"json"};

/** Статьи, которые не являются потерями: по ним подробностей нет. */
const notLosses = new Set(["input","bg","output","useful"]);
/** Синонимы ключей, ведущие на одну страницу подробностей. */
const sameDetail = {efficiency_deviation:"efficiency"};

/** @param {string} name имя столбца на любой из карт потерь @returns {string|null} */
export function lossDetailKey(name) {
  const labels = /** @type {Record<string,string>} */ (dictionary.labels);
  const aliases = /** @type {Record<string,string>} */ (dictionary.aliases);
  const key = name in labels ? name : aliases[name] ?? Object.keys(labels).find(item => labels[item] === name);
  if (!key || notLosses.has(key)) return null;
  return sameDetail[/** @type {keyof typeof sameDetail} */ (key)] ?? key;
}

/** @param {string} name @param {string} from страница, на которую ведёт «Назад» @param {string} [href] */
export function lossDetailHref(name, from, href = location.href) {
  const key = lossDetailKey(name);
  if (!key) return null;
  const url = new URL(href);
  url.searchParams.set("loss", key);
  url.searchParams.set("from", from);
  url.hash = "loss-detail";
  return `${url.pathname}${url.search}${url.hash}`;
}

/** @param {string} href */
export function readLossDetail(href) {
  const params = new URL(href).searchParams;
  return {loss: params.get("loss") ?? "", from: params.get("from") || "losses"};
}

/** Статьи, у которых показатель-основание совпадает с соседней статьёй. */
const sameInspection = {pump_bg:"throttle_loss", na_throttle:"throttle_loss", hydraulic_bg:"throttle_loss", motor:"motor_loss"};

/**
 * Показатель «Меню показателя» (inspection.mjs), к которому относится статья:
 * по нему подбираются источники, формулы и мероприятия.
 * @param {string} key ключ статьи @param {Record<string,{loss?:string}>} inspections
 * @returns {string|undefined}
 */
export function lossInspection(key, inspections) {
  if (key in sameInspection) return sameInspection[/** @type {keyof typeof sameInspection} */ (key)];
  return Object.entries(inspections).find(([name, item]) => name.endsWith("_loss") && item.loss && lossDetailKey(item.loss) === key)?.[0];
}
