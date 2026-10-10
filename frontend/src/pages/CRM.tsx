import { Tooltip } from "../shared/ui/Tooltip";
import { useState } from "react";
import { useResource, segment } from "../shared/api";
import { Plot } from "../charts/Plot";
import { Panel } from "../shared/ui/Panel";
import { Status } from "../shared/ui/Status";
import { Table } from "../shared/ui/Table";
import type { PageProps } from "../shared/ui/context";
import { dateShift, fmt } from "../shared/ui/format";
import { sumDaily, compareDaily } from "./chartData.mjs";
import { MetricCard } from "../shared/ui/MetricCard";
type Run = { code: string; title: string; events: boolean; model?: string };
type Forecast = {
  interval_hours: number;
  by_unit: Record<string, [string, number][]>;
  total: [string, number][];
  partial_days: string[];
  model: string;
  events: boolean;
  error?: string;
};
function useFactOverlay({
  objectId,
  aggregates,
  start,
  end,
}: {
  objectId: string;
  aggregates: string[];
  start: string;
  end: string;
}) {
  const data = useResource<{
    series: { aggregate: string; points: [string, number][] }[];
  }>(
    start && end
      ? `/objects/${segment(objectId)}/crm/fact?aggregates=${segment(aggregates.join(","))}&start=${dateShift(start, -30)}&end=${end}`
      : null,
  );
  return data;
}
export function CRMPage(p: PageProps) {
  const runs = useResource<Run[]>(
    p.objectId ? `/objects/${segment(p.objectId)}/crm/runs` : null,
  );
  const [runChoice, setRun] = useState(""),
    [unitChoice, setUnit] = useState("");
  const run = runs.data?.find((r) => r.code === runChoice) ?? runs.data?.[0];
  const data = useResource<Forecast>(
    run
      ? `/objects/${segment(p.objectId)}/crm/runs/${segment(run.code)}`
      : null,
  );
  const units = Object.keys(data.data?.by_unit ?? {}).sort();
  const unit = units.includes(unitChoice) ? unitChoice : "";
  const predicted = (unit ? data.data?.by_unit[unit] : data.data?.total) ?? [];
  const fact = useFactOverlay({
    objectId: p.objectId,
    aggregates: unit ? [unit] : units,
    start: predicted[0]?.[0] ?? "",
    end: predicted.at(-1)?.[0] ?? "",
  });
  const observed = sumDaily(fact.data?.series.flatMap((s) => s.points) ?? []);
  const comparison = compareDaily(predicted, observed);
  return (
    <Panel
      title="Прогноз подачи по CRM"
      caption="Прогноз внешней модели"
      help="Выгрузка CRM сопоставляется с фактической подачей тех же агрегатов."
    >
      <Status {...runs} />
      {runs.data?.length === 0 && (
        <p className="notice">Нет прогонов CRM для этого объекта.</p>
      )}
      {run && (
        <>
          <div className="page-controls">
            <label>
              Сценарий прогноза
              <select
                aria-label="Сценарий CRM"
                value={run.code}
                onChange={(e) => {
                  setRun(e.target.value);
                  setUnit("");
                }}
              >
                {runs.data?.map((r) => (
                  <option key={r.code} value={r.code}>
                    {r.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Показатель
              <select
                aria-label="Показатель CRM"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
              >
                <option value="">Станция (сумма)</option>
                {units.map((u) => (
                  <option key={u}>{u}</option>
                ))}
              </select>
            </label>
          </div>
          <Status {...data} />
          {data.data?.error && (
            <p className="notice error">{data.data.error}</p>
          )}
          {data.data && !data.data.error && (
            <>
              {predicted.length === 0 ? (
                <p className="notice">В выгрузке нет полных суток прогноза.</p>
              ) : (
                <>
                  <p className="muted">
                    <Tooltip label="Модель CRM" content={`Модель: ${data.data.model || "не указана"}. Шаг выгрузки: ${fmt(data.data.interval_hours)} ч.`} />{" "}
                    {data.data.events
                      ? "Сценарий с событиями"
                      : "Базовый сценарий"}{" "}

                  </p>
                  <div className="metric-group"><div className="kpis">
                    <MetricCard label="Прогноз на общих датах" value={comparison.forecastMean} unit="м³/сут" digits={0}
                      help="Средняя прогнозная подача только за даты, для которых есть фактические измерения." />
                    <MetricCard label="Факт на общих датах" value={comparison.factMean} unit="м³/сут" digits={0}
                      help="Средняя фактическая подача за те же даты, которые использованы в карточке прогноза." />
                  </div></div>
                  {comparison.count > 0 && <p className="muted">Общие даты: {comparison.first} — {comparison.last}; суток с данными: {comparison.count}.</p>}
                  <Status {...fact} />
                  {!fact.loading && !fact.error && comparison.count === 0 && <p className="notice">Нет общих дат для сравнения прогноза и факта. Выберите другой сценарий или агрегат.</p>}
                  <Plot
                    title="CRM и фактическая подача"
                    data={[
                      {
                        type: "scatter",
                        mode: "lines",
                        name: "Факт (телеметрия)",
                        x: observed.map((x) => x[0]),
                        y: observed.map((x) => x[1]),
                        line: { color: "var(--chart-primary)" },
                      },
                      {
                        type: "scatter",
                        mode: "lines",
                        name: "Прогноз CRM",
                        x: predicted.map((x) => x[0]),
                        y: predicted.map((x) => x[1]),
                        line: { color: "var(--chart-status-warning)" },
                      },
                    ]}
                    layout={{
                      xaxis: { type: "date" },
                      yaxis: { title: { text: "Подача, м³/сут" } },
                      ...(observed.length
                        ? {
                            shapes: [
                              {
                                type: "line",
                                xref: "x",
                                x0: observed.at(-1)![0],
                                x1: observed.at(-1)![0],
                                yref: "paper",
                                y0: 0,
                                y1: 1,
                                line: { dash: "dot", color: "var(--chart-secondary)" },
                              },
                            ],
                          }
                        : {}),
                    }}
                  />
                  <p className="muted">
                    {data.data.partial_days.length > 0 && <>Неполные сутки исключены: {data.data.partial_days.length}. </>}
                    <Tooltip label="Сопоставление CRM с фактом" content="Показаны 30 суток факта до начала прогноза. Пунктир — последние измеренные сутки. Неполные сутки выгрузки не участвуют в сравнении." />
                  </p>
                  <details>
                    <summary>Суточный прогноз</summary>
                    <Table
                      rows={predicted.map(([date, value]) => ({ date, value }))}
                      columns={[
                        { key: "date", label: "Дата" },
                        { key: "value", label: "Прогноз, м³/сут" },
                      ]}
                    />
                  </details>
                </>
              )}
            </>
          )}
        </>
      )}
    </Panel>
  );
}
