const precision = {
  '%': 1, 'о.е.': 3, 'кВт·ч/м³': 3, 'МПа': 2,
  'кВт·ч': 0, 'кВт·ч/год': 0, '₽': 0, '₽/год': 0,
  'тыс. ₽': 2, 'тыс. ₽/год': 2,
  'м': 1, 'м³': 1, 'м³/ч': 1, 'м³/сут': 1, 'кВт': 1, 'ч': 1,
};

/** @param {unknown} value @param {number} [digits] */
export function formatNumber(value, digits = 2) {
  if (value == null || (typeof value === 'number' && !Number.isFinite(value))) return '—';
  return typeof value === 'number'
    ? new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(value)
    : String(value);
}

/** @param {unknown} value @param {string} unit @param {number} [digits] */
export function formatMetric(value, unit, digits) {
  return formatNumber(value, digits ?? precision[unit] ?? 2);
}

/** @param {unknown} value */
export function efficiencyPercent(value) {
  return typeof value === 'number' ? value * 100 : null;
}

/** @param {unknown} value */
export function formatEfficiency(value) {
  const result = formatMetric(efficiencyPercent(value), '%');
  return result === '—' ? result : `${result} %`;
}
