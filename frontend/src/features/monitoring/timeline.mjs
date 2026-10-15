/** @template {{snapshot_timestamp?:string|null,quality?:string}} T @param {T[]} points */
export function timelineFocus(points) {
  return points.findLast(point => point.snapshot_timestamp) ?? points.findLast(point => point.quality !== 'missing');
}

/** @template {{[key:string]:unknown}} T @param {T[]} points @param {string} key */
export function latestMetricPoint(points, key) {
  return points.findLast(point => typeof point[key] === 'number' && Number.isFinite(point[key]));
}

/** @param {string} latest @param {number} days */
export function recentPeriod(latest, days) {
  const end = latest.slice(0, 10);
  const first = new Date(`${end}T00:00:00Z`);
  first.setUTCDate(first.getUTCDate() - days + 1);
  return { start: first.toISOString().slice(0, 10), end };
}

/** @param {{timestamp:string, basis?:string, [key:string]:unknown}[]} points @param {string} key @param {number} hours */
export function timelineSignal(points, key, hours) {
  /** @type {{timestamp:string,value:number|null}[]} */
  const result = [];
  const calculationMetric = ['sec_kwh_m3', 'efficiency', 'volume_m3', 'energy_kwh'].includes(key);
  const samples = points.filter(point => {
    const value = point[key];
    if (typeof value === 'number' && Number.isFinite(value)) return true;
    // Partial union rows may contain only a different sensor, not a missing value for this metric.
    return point.quality !== 'partial' || (calculationMetric && (point.basis === 'daily' || point.basis === 'interval'));
  });
  samples.forEach((point, index) => {
    const previous = samples[index - 1];
    if (previous) {
      const start = new Date(previous.timestamp).getTime();
      const end = new Date(point.timestamp).getTime();
      const cadence = calculationMetric && previous.basis === 'daily' && point.basis === 'daily' ? 24 : hours;
      if (end - start > cadence * 3600000 * 1.5 || (calculationMetric && previous.basis && point.basis && previous.basis !== point.basis))
        result.push({ timestamp: new Date((start + end) / 2).toISOString(), value: null });
    }
    const value = point[key];
    result.push({ timestamp: point.timestamp, value: typeof value === 'number' && Number.isFinite(value) ? value : null });
  });
  return result;
}
