import { Tooltip } from "../shared/ui/Tooltip";
import { useState } from "react";
import { useResource, segment } from "../shared/api";
import { Plot, type Trace } from "../charts/Plot";
import { forecastTraces } from "./chartData.mjs";
import { Panel } from "../shared/ui/Panel";
import { Range } from "../shared/ui/Range";
import { Status } from "../shared/ui/Status";
import { Table } from "../shared/ui/Table";
import { dateShift, fmt } from "../shared/ui/format";
import type { PageProps } from "../shared/ui/context";
type Forecast = {
  history: { period: number; value: number }[];
  forecast: { period: number; value: number; lower: number; upper: number }[];
  trend_slope: number;
  naive_baseline: number;
  method: string;
  estimate: boolean;
  note: string;
  period_days: number;
};
export function ForecastPage(p: PageProps) {
  const dates = useResource<{ dates: string[]; default_date: string | null }>(
    p.objectId && p.aggregateId
      ? `/objects/${segment(p.objectId)}/aggregates/${segment(p.aggregateId)}/dates`
      : null,
  );
  const [startChoice, setStart] = useState(""),
    [endChoice, setEnd] = useState(""),
    [period, setPeriod] = useState(30),
    [horizon, setHorizon] = useState(36);
  const start = startChoice || dates.data?.dates[0] || dateShift(p.day, -90),
    end = endChoice || dates.data?.dates.at(-1) || p.day;
  const resource = useResource<Forecast>(
    p.objectId &&
      p.aggregateId &&
      start &&
      end &&
      start <= end &&
      horizon >= 1 &&
      horizon <= 3660
      ? `/objects/${segment(p.objectId)}/aggregates/${segment(p.aggregateId)}/forecast?start=${start}&end=${end}&period_days=${period}&horizon=${horizon}`
      : null,
  );
  const data = resource.data;
  return (
    <Panel
      title="Прогноз объёма закачки"
      caption="Сценарный прогноз по измеренным объёмам"
      help="Экстраполяция тренда — ориентир для сценария, не гидродинамическая модель пласта."
    >
      <div className="page-controls">
        <Range start={start} end={end} onStart={setStart} onEnd={setEnd} />
        <label>
          Периодичность
          <select
            aria-label="Периодичность"
            value={period}
            onChange={(e) => {
              const n = Number(e.target.value);
              setPeriod(n);
              setHorizon(n === 30 ? 36 : n === 7 ? 52 : 1095);
            }}
          >
            <option value={1}>Сутки</option>
            <option value={7}>Неделя</option>
            <option value={30}>Месяц</option>
          </select>
        </label>
        <label>
          Горизонт, периодов
          <input
            aria-label="Горизонт прогноза"
            type="number"
            min={1}
            max={3660}
            value={horizon}
            onChange={(e) => setHorizon(Number(e.target.value))}
          />
        </label>
      </div>
      <Status {...dates} />
      {start > end ? (
        <p className="notice error">
          Начало периода должно быть не позже конца.
        </p>
      ) : (
        <Status {...resource} />
      )}
      {data && (
        <>
          <div className="page-kpis">
            <div>
              Тренд, м³/период<Tooltip label="Тренд" content="Изменение объёма за один выбранный период: сутки, неделю или месяц." /><strong>{fmt(data.trend_slope)}</strong>
            </div>
            <div>
              Базовый ориентир, м³<Tooltip label="Базовый ориентир" content="Среднее последних измеренных периодов, повторённое на будущие периоды без изменения тренда." /><strong>{fmt(data.naive_baseline, 0)}</strong>
            </div>
            <div>
              Прогноз последнего периода, м³
              <strong>{fmt(data.forecast.at(-1)?.value, 0)}</strong>
            </div>
            <div>
              За весь горизонт, м³
              <strong>
                {fmt(
                  data.forecast.reduce((s, x) => s + x.value, 0),
                  0,
                )}
              </strong>
            </div>
          </div>
          <p className="muted">
            {data.estimate ? "Сценарная оценка" : "По измерениям"}
            <Tooltip label="Метод прогноза" content={<>{data.method}{data.note ? ` · ${data.note}` : ""}</>} />
          </p>
          <Plot
            title="Факт и прогноз закачки"
            data={forecastTraces(data) as Trace[]}
            layout={{
              xaxis: {
                title: { text: `Период (${period} сут); 0 — конец истории` },
              },
              yaxis: { title: { text: "Объём, м³" } },
            }}
          />
          <details>
            <summary>Таблица прогноза</summary>
            <Table
              rows={data.forecast}
              columns={[
                { key: "period", label: "Период" },
                { key: "value", label: "Прогноз, м³" },
                { key: "lower", label: "Нижняя граница" },
                { key: "upper", label: "Верхняя граница" },
              ]}
            />
          </details>
        </>
      )}
    </Panel>
  );
}
