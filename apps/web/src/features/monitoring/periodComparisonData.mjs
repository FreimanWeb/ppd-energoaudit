import { timelineSignal } from "./timeline.mjs";

const dayMs = 86400000;
function days(start, end) {
  const a = Date.parse(`${start}T00:00:00Z`), b = Date.parse(`${end}T00:00:00Z`);
  return Number.isFinite(a) && Number.isFinite(b) && b >= a ? (b - a) / dayMs + 1 : 0;
}
export function previousPeriod(start, end) {
  const count = days(start, end);
  if (!count) return null;
  const a = Date.parse(`${start}T00:00:00Z`);
  return {start: new Date(a - count * dayMs).toISOString().slice(0,10), end: new Date(a - dayMs).toISOString().slice(0,10)};
}
const valid = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
/** @param {Record<string, any>[]} points */
export function summarizePeriod(points, start, end, intervalHours = 2) {
  const bases = new Set(points.filter(p => p.basis === 'daily' || p.basis === 'interval').map(p => p.basis));
  const basis = bases.size > 1 ? 'mixed' : [...bases][0] ?? 'none';
  const paired = basis === 'mixed' ? [] : points.filter(p => p.basis === basis && (basis === 'daily'
    ? valid(p.energy_kwh) && valid(p.volume_m3) && p.volume_m3 > 0
    : basis === 'interval' && valid(p.power_kw) && valid(p.flow_m3h) && p.flow_m3h > 0));
  const numerator = paired.reduce((sum,p) => sum + (basis === 'daily' ? p.energy_kwh : p.power_kw),0);
  const denominator = paired.reduce((sum,p) => sum + (basis === 'daily' ? p.volume_m3 : p.flow_m3h),0);
  const average = key => {
    const samples = points.filter(p => valid(p[key]));
    return samples.length ? samples.reduce((sum,p) => sum + p[key],0) / samples.length : null;
  };
  return {
    basis, paired: paired.length,
    expected: basis === 'daily' ? days(start,end) : basis === 'interval' ? days(start,end) * 24 / intervalHours : null,
    sec: paired.length && denominator > 0 ? numerator / denominator : null,
    energy: basis === 'daily' && paired.length ? numerator : null,
    volume: basis === 'daily' && paired.length ? denominator : null,
    flow: average('flow_m3h'), power: average('power_kw'), inlet: average('p_in_mpa'), outlet: average('p_out_mpa'),
    stopped: points.filter(p => p.basis === 'interval' && p.flow_m3h === 0).length,
  };
}
export function periodChange(before, after) {
  return valid(before) && before > 0 && valid(after) ? (after / before - 1) * 100 : null;
}

/** @param {Record<string, any>[]} points */
export function comparisonProfile(points, start, basis, intervalHours = 2) {
  const originals = new Map();
  const samples = points.filter(p => p.basis === basis || p.quality === 'missing').map(p => {
    // Telemetry dates are local wall-clock values; UTC here keeps calendar alignment independent of the browser timezone.
    const timestamp = basis === 'daily' ? `${p.timestamp.slice(0,10)}T00:00:00Z` : `${p.timestamp.slice(0,19)}Z`;
    originals.set(timestamp,p.timestamp);
    const numerator = basis === 'daily' ? p.energy_kwh : p.power_kw;
    const denominator = basis === 'daily' ? p.volume_m3 : p.flow_m3h;
    return {timestamp,basis,quality:p.quality,sec_kwh_m3:valid(numerator) && valid(denominator) && denominator > 0 ? numerator / denominator : null};
  });
  const origin = Date.parse(`${start}T00:00:00Z`);
  return timelineSignal(samples,'sec_kwh_m3',intervalHours).map(p=>({
    day:(Date.parse(p.timestamp)-origin)/dayMs, value:p.value, timestamp:originals.get(p.timestamp) ?? p.timestamp,
  }));
}
