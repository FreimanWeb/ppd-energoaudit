/** @param {string} text */
export function parseEquipmentNumber(text) {
  const value = text.trim().replace(",", ".");
  return value ? Number(value) : null;
}

/** @param {unknown} left @param {unknown} right */
export function sameParameterValue(left, right) {
  if (left == null || right == null) return left == null && right == null;
  if (Array.isArray(left) || Array.isArray(right))
    return Array.isArray(left) && Array.isArray(right) && left.length === right.length
      && left.every((value, index) => sameParameterValue(value, right[index]));
  if (typeof left === "object" && typeof right === "object") {
    const a = /** @type {Record<string, unknown>} */ (left);
    const b = /** @type {Record<string, unknown>} */ (right);
    return Object.keys(a).length === Object.keys(b).length
      && Object.keys(a).every(key => Object.hasOwn(b, key) && sameParameterValue(a[key], b[key]));
  }
  return left === right;
}

/** @param {Record<string, unknown>} before @param {Record<string, unknown>} after */
export function parameterDifferences(before, after) {
  return Object.keys(after).filter(key => !sameParameterValue(before[key], after[key]))
    .map(key => ({key, before: before[key] ?? null, after: after[key] ?? null}));
}

/** Corrections retain their complete declared set; replacement describes a new physical unit.
 * @param {Record<string, unknown>} before
 * @param {Record<string, unknown>} after
 * @param {string} reason
 */
export function journalPatch(before, after, reason) {
  if (reason === "correction") return {...after};
  if (reason === "replacement") return Object.fromEntries(Object.entries(after)
    .filter(([, value]) => value != null && value !== "" && !(Array.isArray(value) && !value.length)));
  return Object.fromEntries(parameterDifferences(before, after).map(row => [row.key, row.after]));
}

/** Local plant time: normalize minute/date inputs without applying a browser timezone.
 * @param {string} value */
export function normalizeEquipmentTime(value) {
  const complete = value.length === 10 ? `${value}T00:00:00` : value.length === 16 ? `${value}:00` : value;
  return complete.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}
