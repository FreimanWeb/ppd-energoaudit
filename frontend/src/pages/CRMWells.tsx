import { Tooltip } from "../shared/ui/Tooltip";
import { useState } from "react";
import { useResource, segment } from "../shared/api";
import { Plot, type Trace } from "../charts/Plot";
import { Panel } from "../shared/ui/Panel";
import { Status } from "../shared/ui/Status";
import { Table } from "../shared/ui/Table";
import type { PageProps } from "../shared/ui/context";
import { fmt } from "../shared/ui/format";
import { filterEdges, downtimeForWell } from "./chartData.mjs";
type WellRow = {
  month: string;
  well?: string;
  well_key?: string;
  base: number | null;
  forecast: number | null;
  fact: number | null;
  deviation?: number | null;
  share?: number | null;
  r_ust?: number | null;
  r_ust_fact?: number | null;
};
type Report = {
  months: string[];
  wells: string[];
  has_fact: boolean;
  totals: WellRow[];
  rows: WellRow[];
  error?: string;
};
type Graph = {
  edges: { source: string; target: string; strength: number }[];
  positions: Record<string, [number, number]>;
  by_well: Record<string, { target: string; strength: number }[]>;
  centrality: {
    well: string;
    strength_sum: number;
    degree: number;
    betweenness: number;
    top_neighbor: string;
    top_neighbor_strength: number;
  }[];
  error?: string;
};
type Downtime = {
  well: string;
  well_key?: string;
  since: string | null;
  reason: string;
  [key: string]: unknown;
};
type Monthly = {series:WellRow[];downtime_marks:Downtime[];window:[string,string]|null;last:WellRow|null};
export function CRMWellsPage(p: PageProps) {
  const runs = useResource<{ code: string; title: string; mode: string }[]>(
    p.objectId ? `/objects/${segment(p.objectId)}/crm/well-runs` : null,
  );
  const [task, setTask] = useState<"injection" | "connections" | "downtime">("injection");
  const [runChoice, setRun] = useState(""),
    [wellChoice, setWell] = useState(""),
    [monthChoice, setMonth] = useState(""),
    [threshold, setThreshold] = useState(0),
    [graphWell, setGraphWell] = useState("");
  const run = runs.data?.find((r) => r.code === runChoice) ?? runs.data?.[0],
    base = run
      ? `/objects/${segment(p.objectId)}/crm/well-runs/${segment(run.code)}`
      : null;
  const resource = useResource<Report>(base),
    network = useResource<Graph>(base ? `${base}/graph?edge_limit=60` : null),
    downtime = useResource<Downtime[]>(
      p.objectId ? `/objects/${segment(p.objectId)}/well-downtime` : null,
    );
  const report = resource.data?.error ? undefined : resource.data;
  const well = report?.wells.includes(wellChoice) ? wellChoice : "",
    month = report?.months.includes(monthChoice)
      ? monthChoice
      : (report?.months.at(-1) ?? "");
  const monthly=useResource<Monthly>(base?`${base}/monthly${well?`?well=${segment(well)}`:''}`:null);
  const totals=monthly.data?.series??[],last=monthly.data?.last;
  const rows=report?.rows.filter(r=>r.month===month)??[];
  const marks=monthly.data?.downtime_marks??[];
  const graph = network.data,
    selected =
      graph?.positions && graphWell in graph.positions ? graphWell : "",
    edges = filterEdges(graph?.edges ?? [], threshold, selected),
    positions = graph?.positions ?? {},
    allWells = Object.keys(positions);
  const selectedDowntime=downtimeForWell(selected,report?.rows??[],downtime.data??[]);
  const traces: Trace[] = edges.map((edge) => ({
    type: "scatter",
    mode: "lines",
    x: [positions[edge.source]?.[0], positions[edge.target]?.[0]],
    y: [positions[edge.source]?.[1], positions[edge.target]?.[1]],
    line: { width: 1 + edge.strength * 3, color: "var(--chart-secondary-alt)" },
    text: `${edge.source} ↔ ${edge.target}: ${fmt(edge.strength, 3)}`,
    hoverinfo: "text",
    showlegend: false,
  }));
  if (allWells.length)
    traces.push({
      type: "scatter",
      mode: "text+markers",
      x: allWells.map((w) => positions[w][0]),
      y: allWells.map((w) => positions[w][1]),
      text: allWells,
      customdata: allWells,
      textposition: "top center",
      marker: {
        symbol: allWells.map(w=>downtimeForWell(w,report?.rows??[],downtime.data??[])?"square":"circle"),
        size: allWells.map((w) => (w === selected ? 20 : 12)),
        color: allWells.map((w) =>
          w === selected
            ? "var(--chart-status-warning)"
            : edges.some((e) => e.source === w || e.target === w)
              ? "var(--chart-primary)"
              : "var(--chart-status-neutral)",
        ),
      },
      hovertext:allWells.map(w=>downtimeForWell(w,report?.rows??[],downtime.data??[])?.reason??"Причина простоя не указана"),
      hovertemplate: "Скважина %{text}<br>%{hovertext}<extra></extra>",
      showlegend: false,
    });
  return (
    <Panel
      title="CRM по скважинам"
      help="Месячный прогноз, фактическая закачка и взаимовлияние нагнетательных скважин по выгрузке CRM."
    >
      <Status {...runs} />
      {runs.data?.length === 0 && (
        <p className="notice">
          Нет выгрузок CRM по скважинам для этого объекта.
        </p>
      )}
      {run && (
        <>
          <div className="page-controls">
            <label>
              Сценарий
              <select
                aria-label="Сценарий скважин"
                value={run.code}
                onChange={(e) => {
                  setRun(e.target.value);
                  setWell("");
                  setMonth("");
                  setGraphWell("");
                }}
              >
                {runs.data?.map((r) => (
                  <option key={r.code} value={r.code}>
                    {r.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <Status {...resource} />
          {resource.data?.error && (
            <p className="notice error">{resource.data.error}</p>
          )}
          {report && !report.error && (
            <>
              <div className="metric-segments" role="group" aria-label="Задача CRM по скважинам">
                <button type="button" aria-pressed={task === "injection"} onClick={() => setTask("injection")}>Закачка</button>
                <button type="button" aria-pressed={task === "connections"} onClick={() => setTask("connections")}>Связи</button>
                <button type="button" aria-pressed={task === "downtime"} onClick={() => setTask("downtime")}>Простои</button>
              </div>
              {task === "injection" && <section aria-label="Закачка скважин">
                <div className="page-controls">
            <label>
              Скважина
              <select
                aria-label="Скважина"
                value={well}
                onChange={(e) => setWell(e.target.value)}
              >
                <option value="">Все скважины (сумма)</option>
                {report?.wells.map((w) => (
                  <option key={w}>{w}</option>
                ))}
              </select>
            </label>
                </div>
              <Status {...monthly}/>
              {totals.length ? (
                <>
                  <div className="page-kpis">
                    <div>
                      Прогноз последнего месяца, м³
                      <strong>{fmt(last?.forecast, 0)}</strong>
                    </div>
                    <div>
                      Факт, м³<strong>{fmt(last?.fact, 0)}</strong>
                    </div>
                    <div>
                      Отклонение, %
                      <strong>
                        {last?.fact && last.forecast !== null
                          ? fmt(((last.forecast - last.fact) / last.fact) * 100)
                          : "—"}
                      </strong>
                    </div>
                  </div>
                  <Plot
                    title="Месячная закачка скважин"
                    data={(["base", "forecast", "fact"] as const).map(
                      (key, i) => ({
                        type: "scatter",
                        mode: "lines+markers",
                        name: ["Базовый прогноз", "Сценарий", "Факт"][i],
                        x: totals.map((t) => t.month),
                        y: totals.map((t) => t[key]),
                        connectgaps: false,
                        line: { color: ["var(--chart-secondary-alt)", "var(--chart-status-warning)", "var(--chart-primary)"][i] },
                      }),
                    )}
                    layout={{
                      xaxis: { type: "date", tickformat: "%m.%Y", ...(monthly.data?.window?{range:monthly.data.window}:{}) },
                      yaxis: { title: { text: "Закачка, м³/мес" } },
                      annotations: marks.map(d=>({x:d.since!,xref:'x',y:1,yref:'paper',text:`${d.well}: ${d.reason}`.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),showarrow:false,textangle:"90",xanchor:'left',yanchor:'top',font:{size:10,color:'var(--chart-status-danger)'}})),
                      shapes: marks.map((d) => ({
                        type: "line",
                        xref: "x",
                        x0: d.since!,
                        x1: d.since!,
                        yref: "paper",
                        y0: 0,
                        y1: 1,
                        line: { dash: "dot", color: "var(--chart-status-danger)" },
                      })),
                    }}
                  />
                  <Tooltip label="Месячная закачка скважин" content="Красный пунктир — начало простоя. Отсутствующий факт показан как пропуск, а не нулевое значение." />
                  {marks.length>0&&<ul className="warnings" aria-label="Простои в показанном периоде">{marks.map((d,i)=><li key={`${d.well}-${i}`}>{d.well}: {d.reason} · {d.since}</li>)}</ul>}
                </>
              ) : (
                <p className="notice">
                  Для выбранной скважины нет месячных данных.
                </p>
              )}
              <details>
                <summary>Месячный отчёт по всем скважинам</summary>
              <label className="compact-control">
                Месяц
                <select
                  aria-label="Месяц"
                  value={month}
                  onChange={(e) => setMonth(e.target.value)}
                >
                  {report.months.map((m) => (
                    <option key={m}>{m}</option>
                  ))}
                </select>
              </label>
              <Table
                rows={rows.map((row) => {
                  const d = downtime.data?.find(
                    (d) =>
                      (d.well_key ?? d.well) === (row.well_key ?? row.well),
                  );
                  return {
                    ...row,
                    share: row.share == null ? null : row.share * 100,
                    reason: d?.reason,
                    since: d?.since,
                  };
                })}
                columns={[
                  { key: "well", label: "Скважина" },
                  { key: "forecast", label: "Прогноз, м³/мес" },
                  { key: "fact", label: "Факт, м³/мес" },
                  { key: "deviation", label: "Отклонение, %" },
                  { key: "share", label: "Доля, %" },
                  { key: "r_ust", label: "Руст, атм", help: "Устьевое давление по прогнозной модели, в атмосферах." },
                  { key: "r_ust_fact", label: "Руст факт, атм", help: "Измеренное устьевое давление, в атмосферах." },
                  { key: "reason", label: "Причина простоя" },
                  { key: "since", label: "Простой с" },
                ]}
              />
              </details>
              </section>}
              {task === "connections" && <section aria-label="Связи скважин">
              <h3>Граф взаимовлияния скважин<Tooltip label="Граф взаимовлияния скважин" content="Связи отражают коэффициенты внешней модели и требуют инженерной интерпретации. Квадрат — скважина с указанной причиной простоя; круг — причина простоя не указана, это не подтверждает работу скважины." /></h3>
              <div className="page-controls">
                <label>
                  Узел графа
                  <select
                    aria-label="Скважина графа"
                    value={selected}
                    onChange={(e) => setGraphWell(e.target.value)}
                  >
                    <option value="">Все связи</option>
                    {allWells.map((w) => (
                      <option key={w}>{w}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Порог силы связи: {fmt(threshold)}
                  <input
                    aria-label="Порог силы связи"
                    type="range"
                    min={0}
                    max={1}
                    step={0.01}
                    value={threshold}
                    onChange={(e) => setThreshold(Number(e.target.value))}
                  />
                </label>
              </div>
              <Status {...network} />

              {selected&&<p className="notice" aria-label="Простой выбранной скважины">{selectedDowntime?`${selected}: ${selectedDowntime.reason}${selectedDowntime.since?` · с ${selectedDowntime.since}`:''}`:`Для скважины ${selected} причина простоя не указана.`}</p>}
              {graph?.error ? (
                <p className="notice error">{graph.error}</p>
              ) : (
                graph && (
                  <>
                    {allWells.length ? (
                      <Plot
                        title="Граф взаимовлияния"
                        data={traces}
                        layout={{
                          xaxis: { visible: false },
                          yaxis: { visible: false, scaleanchor: "x" },
                          hovermode: "closest",
                          height: 430,
                        }}
                        onSelect={setGraphWell}
                      />
                    ) : (
                      <p className="notice">
                        Связи скважин в выгрузке отсутствуют.
                      </p>
                    )}
                    <p className="muted">
                      Показаны {edges.length} связей из {graph.edges.length}.
                      Связи по внешней модели.
                    </p>
                    {selected && (
                      <Table
                        rows={(graph.by_well[selected] ?? []).filter(
                          (e) => e.strength >= threshold,
                        )}
                        columns={[
                          { key: "target", label: "Связанная скважина" },
                          { key: "strength", label: "Сила связи", help: "Коэффициент взаимовлияния скважин из внешней CRM-модели." },
                        ]}
                      />
                    )}
                    <details>
                      <summary>Центральность скважин</summary>
                      <Table
                        rows={graph.centrality}
                        columns={[
                          { key: "well", label: "Скважина" },
                          { key: "strength_sum", label: "Сумма сил", help: "Сумма коэффициентов связей этой скважины с соседними узлами графа." },
                          { key: "degree", label: "Связи" },
                          { key: "betweenness", label: "Посредничество", help: "Показывает, насколько часто скважина связывает другие узлы графа по кратчайшим путям." },
                          { key: "top_neighbor", label: "Сильнейшая связь" },
                          { key: "top_neighbor_strength", label: "Её сила" },
                        ]}
                      />
                    </details>
                  </>
                )
              )}
              </section>}
              {task === "downtime" && <section aria-label="Простои скважин">
                <h3>Простои скважин</h3>
                <Status {...downtime} />
                <Table
                  rows={downtime.data ?? []}
                  columns={[
                    { key: "well", label: "Скважина" },
                    { key: "since", label: "Простой с" },
                    { key: "reason", label: "Причина" },
                  ]}
                />
              </section>}
            </>
          )}
        </>
      )}
    </Panel>
  );
}
