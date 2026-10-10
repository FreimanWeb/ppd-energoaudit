import { useState } from "react";
import { TelemetryChart, type TelemetrySignal } from "./TelemetryChart";
import { useResource, segment } from "../shared/api";
import { Panel } from "../shared/ui/Panel";
import { Range } from "../shared/ui/Range";
import { Status } from "../shared/ui/Status";
import { Table } from "../shared/ui/Table";
import { dateShift } from "../shared/ui/format";
import type { PageProps } from "../shared/ui/context";

type Telemetry = {
  records: Record<string, unknown>[];
  series: TelemetrySignal[];
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
  const series = data.data?.series ?? [];
  const pressures = series.filter((signal) => signal.unit === "МПа");
  const primary = series.filter((signal) =>
    signal.unit === "кВт" || signal.unit === "м³/ч",
  );
  const additional = series.filter((signal) =>
    signal.unit !== "МПа" && signal.unit !== "кВт" && signal.unit !== "м³/ч",
  );
  const marker = mode === "day" ? p.timestamp || undefined : undefined;
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
      caption="Исходные измерения"
      help="Давление и мощность показываются ступенями с сохранением последнего известного состояния. Суточные показатели не заменяют мгновенные измерения."
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
          {series.length ? (
            <>
              {pressures.length > 0 && (
                <TelemetryChart title="Давления" series={pressures} timestamp={marker} />
              )}
              {primary.length > 0 && (
                <div className="chart-grid">
                  {primary.map((signal) => (
                    <TelemetryChart key={signal.metric} title={signal.metric} series={[signal]} timestamp={marker} />
                  ))}
                </div>
              )}
              {additional.length > 0 && (
                <details>
                  <summary>Дополнительные измерения ({additional.length})</summary>
                  <div className="chart-grid">
                    {additional.map((signal) => (
                      <TelemetryChart key={signal.metric} title={signal.metric} series={[signal]} timestamp={marker} />
                    ))}
                  </div>
                </details>
              )}
            </>
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
