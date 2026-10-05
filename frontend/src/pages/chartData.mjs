/** @param {{history:{period:number,value:number}[],forecast:{period:number,value:number,lower:number,upper:number}[],naive_baseline:number}} result */
export function forecastTraces(result) {
  const future = result.forecast;
  return [
    {
      type: "scatter",
      mode: "lines+markers",
      name: "Факт",
      x: result.history.map((p) => p.period),
      y: result.history.map((p) => p.value),
      line: { color: "#1f4e4a" },
    },
    {
      type: "scatter",
      mode: "lines",
      name: "Нижняя граница",
      x: future.map((p) => p.period),
      y: future.map((p) => p.lower),
      line: { width: 0 },
      showlegend: false,
    },
    {
      type: "scatter",
      mode: "lines",
      name: "Интервал прогноза",
      x: future.map((p) => p.period),
      y: future.map((p) => p.upper),
      line: { width: 0 },
      fill: "tonexty",
      fillcolor: "rgba(197,139,37,.15)",
    },
    {
      type: "scatter",
      mode: "lines+markers",
      name: "Прогноз",
      x: future.map((p) => p.period),
      y: future.map((p) => p.value),
      line: { color: "#c58b25" },
    },
    {
      type: "scatter",
      mode: "lines",
      name: "Наивный ориентир",
      x: future.map((p) => p.period),
      y: future.map(() => result.naive_baseline),
      line: { color: "#8b9892", dash: "dot" },
    },
  ];
}
/** @template {{month:string,well?:string}} T
 * @param {{totals:T[],rows:T[]}} report @param {string} well */
export function wellSeries(report, well) {
  return well ? report.rows.filter((r) => r.well === well) : report.totals;
}
/** @template {{source:string,target:string,strength:number}} T @param {T[]} edges @param {number} threshold @param {string} selected */
export function filterEdges(edges, threshold, selected = "") {
  return edges.filter(
    (e) =>
      e.strength >= threshold &&
      (!selected || e.source === selected || e.target === selected),
  );
}
/** @param {[string,number][]} rows */
export function sumDaily(rows) {
  const totals = new Map();
  for (const [date, value] of rows)
    totals.set(date, (totals.get(date) ?? 0) + value);
  return [...totals].sort((a, b) => a[0].localeCompare(b[0]));
}

/** @param {string} well
 * @param {{well?:string,well_key?:string}[]} rows
 * @param {{well:string,well_key?:string,reason:string,since:string|null}[]} downtime */
export function downtimeForWell(well,rows,downtime) {
 const key=rows.find(row=>row.well===well)?.well_key??well;
 return downtime.find(item=>(item.well_key??item.well)===key&&item.reason)||null;
}
