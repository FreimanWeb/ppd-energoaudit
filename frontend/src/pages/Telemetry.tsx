import { useState } from "react";
import { signalShape } from "./fidelity.mjs";
import { useResource, segment } from "../api";
import { Plot, type Trace } from "../Plot";
import {
  Panel,
  Range,
  Status,
  Table,
  dateShift,
  type PageProps,
} from "./common";

type Telemetry = {
  records: Record<string, unknown>[];
  series: {
    metric: string;
    unit: string;
    points: { timestamp: string; value: number | null }[];
  }[];
};
export function TelemetryPage(
  p: PageProps & { viewerOnly?: boolean; availableDates?: string[] },
) {
  const [mode, setMode] = useState(p.viewerOnly ? "period" : "day"),
    [startChoice, setStart] = useState(""),
    [endChoice, setEnd] = useState(""),
    [page, setPage] = useState(0);
  const start =
      startChoice ||
      (p.viewerOnly ? p.availableDates?.[0] : undefined) ||
      dateShift(p.day, -30),
    end =
      endChoice ||
      (p.viewerOnly ? p.availableDates?.at(-1) : undefined) ||
      p.day;
  const from = mode === "day" ? p.day : start,
    to = mode === "day" ? p.day : end;
  const data = useResource<Telemetry>(
    p.objectId && p.aggregateId && from && to && from <= to
      ? `/objects/${segment(p.objectId)}/telemetry?aggregate_id=${segment(p.aggregateId)}&start=${from}&end=${to}`
      : null,
  );
  const records = data.data?.records ?? [];
  const columns = records.length
    ? Object.keys(records[0]).map((key) => ({
        key,
        label:
          (
            {
              timestamp: "Момент",
              metric: "Параметр",
              value: "Значение",
              unit: "Единица",
              source: "Источник",
              source_kind: "Источник",
              aggregate_id: "Агрегат",
              aggregate_code: "Агрегат",
              quality_flag: "Качество",
            } as Record<string, string>
          )[key] ?? key,
      }))
    : [];
  const shownPage = Math.min(
    page,
    Math.max(0, Math.ceil(records.length / 200) - 1),
  );
  return (
    <Panel
      title="Телеметрия"
      caption="Исходные измерения. Давление и мощность показываются ступенями с сохранением последнего известного состояния; суточные показатели не заменяют мгновенные измерения."
    >
      <div className="page-controls">
        <label>
          Режим просмотра
          <select
            aria-label="Режим телеметрии"
            value={mode}
            onChange={(e) => {
              setMode(e.target.value);
              setPage(0);
            }}
          >
            <option value="day">Выбранные сутки</option>
            <option value="period">Период</option>
          </select>
        </label>
        {mode === "period" && (
          <Range
            start={start}
            end={end}
            onStart={(v) => {
              setStart(v);
              setPage(0);
            }}
            onEnd={(v) => {
              setEnd(v);
              setPage(0);
            }}
          />
        )}
      </div>
      {!from || !to ? (
        <p className="notice">
          Выберите дату или период для просмотра измерений.
        </p>
      ) : from > to ? (
        <p className="notice error">
          Начало периода должно быть не позже конца.
        </p>
      ) : (
        <Status {...data} />
      )}
      {data.data && (
        <>
          {data.data.series.length ? (
            <div className="chart-grid">
              {data.data.series.map((series) => (
                <div key={series.metric}>
                  <h3>{series.metric}</h3>
                  <Plot
                    title={series.metric}
                    data={[
                      {
                        type: "scatter",
                        mode: "lines+markers",
                        name: series.metric,
                        x: series.points.map((x) => x.timestamp),
                        y: series.points.map((x) => x.value),
                        connectgaps: false,
                        line: {
                          color: "#1f4e4a",
                          shape: signalShape(series.metric, series.unit),
                        },
                      } as Trace,
                    ]}
                    layout={{
                      yaxis: {
                        title: { text: series.unit },
                        gridcolor: "#eef1ef",
                      },
                      xaxis: { type: "date", gridcolor: "#eef1ef" },
                      ...(mode === "day" && p.timestamp
                        ? {
                            shapes: [
                              {
                                type: "line",
                                xref: "x",
                                x0: p.timestamp,
                                x1: p.timestamp,
                                yref: "paper",
                                y0: 0,
                                y1: 1,
                                line: { color: "#c58b25", dash: "dot" },
                              },
                            ],
                          }
                        : {}),
                    }}
                  />
                </div>
              ))}
            </div>
          ) : (
            <p className="notice">Измерений за выбранный период нет.</p>
          )}
          <details>
            <summary>Таблица исходных измерений ({records.length})</summary>
            <Table
              rows={records.slice(shownPage * 200, (shownPage + 1) * 200)}
              columns={columns}
            />
            {records.length > 200 && (
              <div className="page-controls">
                <button
                  disabled={shownPage === 0}
                  onClick={() => setPage(shownPage - 1)}
                >
                  Назад
                </button>
                <span>
                  Страница {shownPage + 1} из {Math.ceil(records.length / 200)}
                </span>
                <button
                  disabled={(shownPage + 1) * 200 >= records.length}
                  onClick={() => setPage(shownPage + 1)}
                >
                  Далее
                </button>
              </div>
            )}
          </details>
        </>
      )}
    </Panel>
  );
}
