import { useState } from "react";
import { useResource, segment } from "../api";
import { Plot } from "../Plot";
import { Panel, Status, Table, dateShift, fmt, type PageProps } from "./common";
import { sumDaily } from "./chartData.mjs";
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
  const overlap = observed.filter(([date]) =>
    predicted.some(([d]) => d === date),
  );
  return (
    <Panel
      title="Прогноз подачи по CRM"
      caption="Выгрузка внешней модели рядом с фактической подачей тех же агрегатов."
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
                    Модель: {data.data.model || "не указана"} ·{" "}
                    {data.data.events
                      ? "Сценарий с событиями"
                      : "Базовый сценарий"}{" "}
                    · шаг выгрузки {fmt(data.data.interval_hours)} ч
                  </p>
                  <div className="page-kpis">
                    <div>
                      Прогноз в среднем, м³/сут
                      <strong>
                        {fmt(
                          predicted.reduce((s, x) => s + x[1], 0) /
                            predicted.length,
                          0,
                        )}
                      </strong>
                    </div>
                    <div>
                      Факт на перекрытии, м³/сут
                      <strong>
                        {overlap.length
                          ? fmt(
                              overlap.reduce((s, x) => s + x[1], 0) /
                                overlap.length,
                              0,
                            )
                          : "—"}
                      </strong>
                    </div>
                  </div>
                  <Status {...fact} />
                  <Plot
                    title="CRM и фактическая подача"
                    data={[
                      {
                        type: "scatter",
                        mode: "lines",
                        name: "Факт (телеметрия)",
                        x: observed.map((x) => x[0]),
                        y: observed.map((x) => x[1]),
                        line: { color: "#1f4e4a" },
                      },
                      {
                        type: "scatter",
                        mode: "lines",
                        name: "Прогноз CRM",
                        x: predicted.map((x) => x[0]),
                        y: predicted.map((x) => x[1]),
                        line: { color: "#c58b25" },
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
                                line: { dash: "dot", color: "#8b9892" },
                              },
                            ],
                          }
                        : {}),
                    }}
                  />
                  <p className="muted">
                    Показаны 30 суток факта до начала прогноза. Пунктир —
                    последние измеренные сутки. Частичные сутки выгрузки
                    исключены: {data.data.partial_days.length}.
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
