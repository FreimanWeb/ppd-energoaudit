import { recentPeriod } from './timeline.mjs';

/** @param {{timestamp:string,value:number|null}[]} history @param {string|null} endDate @param {number} days */
export function portfolioHistory(history, endDate, days) {
  if (!endDate) return {start:'', end:'', history:[]};
  const {start, end} = recentPeriod(endDate, days);
  return {start, end, history:history.filter(point => point.timestamp.slice(0, 10) >= start && point.timestamp.slice(0, 10) <= end)};
}

/**
 * @template {{code:string,name:string,ngdu_name:string,water_type:string,status:string}} T
 * @param {T[]} objects @param {string} query @param {string[]} ngdu @param {string[]} water @param {string} status
 */
export function visibleObjects(objects, query, ngdu, water, status) {
  const search = query.trim().toLocaleLowerCase('ru');
  const rank = {attention:0, normal:1, unknown:2};
  return objects.filter(object =>
    (!search || `${object.code} ${object.name} ${object.ngdu_name}`.toLocaleLowerCase('ru').includes(search)) &&
    (!ngdu.length || ngdu.includes(object.ngdu_name)) &&
    (!water.length || water.includes(object.water_type)) &&
    (status === 'all' || object.status === status)
  ).sort((a,b) => rank[a.status] - rank[b.status] || a.name.localeCompare(b.name, 'ru'));
}

/** @param {{timestamp:string,value:number|null}[]} history @param {number} width @param {number} height @param {{start:string,end:string}} [period] */
export function sparklinePoints(history, width = 240, height = 64, period) {
  const timestamps = history.map(point => new Date(point.timestamp).getTime());
  const validTimes = timestamps.filter(Number.isFinite);
  const values = history.flatMap(point => point.value != null && Number.isFinite(point.value) ? [point.value] : []);
  const start = period ? new Date(`${period.start}T00:00:00`).getTime() : Math.min(...validTimes);
  const end = period ? new Date(`${period.end}T23:59:59.999`).getTime() : Math.max(...validTimes);
  const low = Math.min(...values), high = Math.max(...values);
  return history.map((point,index) => point.value == null || !Number.isFinite(point.value) || !Number.isFinite(timestamps[index]) ? null : {
    x: start === end ? width / 2 : 8 + (timestamps[index] - start) / (end - start) * (width - 16),
    y: (low === high ? 32 : 54 - (point.value - low) / (high - low) * 44) * height / 64,
  });
}

/** @param {({x:number}|null)[]} points @param {number} x */
export function nearestSparklinePoint(points, x) {
  let nearest = null, distance = Infinity;
  points.forEach((point, index) => {
    if (point && Math.abs(point.x - x) < distance) {
      nearest = index;
      distance = Math.abs(point.x - x);
    }
  });
  return nearest;
}
