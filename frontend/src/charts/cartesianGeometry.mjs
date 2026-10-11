/** Display geometry only: no energy, financial or hydraulic calculations. */
/** @param {any} model @param {string[]} hidden @param {[number,number]|null} viewport */
export function barIntervals(model, hidden = [], viewport = null) {
  if (model.variant === "waterfall")
    return (model.waterfall ?? []).map((point, index) => ({
      series: { id: "waterfall", name: point.label, color: point.color },
      point: {
        x: point.label,
        y: point.value,
        label: point.label,
        color: point.color,
        tooltip: point.tooltip,
        customdata: point.tooltip?.selection,
      },
      start: point.start,
      end: point.end,
      value: point.value,
      index,
      seriesIndex: 0,
      count: 1,
    }));
  const visible = model.series.filter(
    (series) => series.type === "bar" && !hidden.includes(series.id),
  );
  const sums = new Map();
  const bars = [];
  visible.forEach((series, seriesIndex) =>
    series.points.forEach((point, index) => {
      if (point.y == null || !Number.isFinite(point.y)) return;
      if (
        viewport &&
        typeof point.x === "number" &&
        (point.x < viewport[0] || point.x > viewport[1])
      )
        return;
      const sumsForCategory = sums.get(point.x) ?? { positive: 0, negative: 0 };
      const sign = point.y >= 0 ? "positive" : "negative";
      const start = model.stacked ? sumsForCategory[sign] : 0;
      const end = start + point.y;
      if (model.stacked) {
        sumsForCategory[sign] = end;
        sums.set(point.x, sumsForCategory);
      }
      bars.push({
        series,
        point,
        start,
        end,
        value: point.y,
        index,
        seriesIndex,
        count: visible.length,
      });
    }),
  );
  return bars;
}
/** @param {any[]} points @param {boolean} connectNulls */
export function lineRuns(points, connectNulls = false) {
  const runs = [];
  let current = [];
  for (const point of points) {
    if (point.y != null && Number.isFinite(point.y)) current.push(point);
    else if (!connectNulls && current.length) {
      runs.push(current);
      current = [];
    }
  }
  if (current.length) runs.push(current);
  return runs;
}
/** Keep boundary neighbours so a clipped curve still reaches the viewport edges. */
/** @param {any[]} points @param {[number,number]|null} viewport */
export function viewPoints(points, viewport = null) {
  if (!viewport || !points.length || typeof points[0].x !== "number")
    return points;
  let first = points.findIndex((point) => point.x >= viewport[0]);
  if (first < 0) first = points.length;
  let last = points.findIndex((point) => point.x > viewport[1]);
  if (last < 0) last = points.length;
  return points.slice(
    Math.max(0, first - 1),
    Math.min(points.length, last + 1),
  );
}
/** @param {any} model @param {string[]} hidden @param {[number,number]|null} viewport */
export function chartDomains(model, hidden = [], viewport = null) {
  const visible = model.series.filter((series) => !hidden.includes(series.id));
  const allPoints = visible.flatMap((series) => series.points);
  const shown = visible.flatMap((series) =>
    viewPoints(series.points, viewport),
  );
  const categories = [
    ...new Set(
      model.variant === "waterfall"
        ? (model.waterfall ?? []).map((point) => point.label)
        : allPoints.map((point) => point.x),
    ),
  ];
  const bars = barIntervals(model, hidden, viewport);
  const values = [
    ...shown.flatMap((point) => [point.y, point.low, point.high]),
    ...bars.flatMap((bar) => [bar.start, bar.end]),
  ].filter((value) => typeof value === "number" && Number.isFinite(value));
  const coordinates = allPoints
    .map((point) => point.x)
    .filter((value) => typeof value === "number" && Number.isFinite(value));
  const xValues = model.horizontal ? values : coordinates;
  const yValues = model.horizontal ? coordinates : values;
  for (const reference of model.references) {
    if (typeof reference.value === "number" && Number.isFinite(reference.value))
      (reference.axis === "x" ? xValues : yValues).push(reference.value);
  }
  const hasBars =
    model.variant === "waterfall" ||
    visible.some((series) => series.type === "bar");
  function domain(axis, items, isValueAxis) {
    if (axis.type === "category") return categories;
    if (!model.horizontal && axis === model.xAxis && viewport) return viewport;
    if (axis.domain && axis.domain.every((value) => typeof value === "number"))
      return axis.domain;
    if (!items.length) return [0, 1];
    let min = Math.min(...items),
      max = Math.max(...items);
    if (hasBars && isValueAxis) {
      min = Math.min(0, min);
      max = Math.max(0, max);
    }
    if (min === max) {
      const padding = Math.max(Math.abs(min) * 0.1, 1);
      min -= padding;
      max += padding;
    }
    return [min, max];
  }
  return {
    x: domain(model.xAxis, xValues, model.horizontal),
    y: domain(model.yAxis, yValues, !model.horizontal),
  };
}
