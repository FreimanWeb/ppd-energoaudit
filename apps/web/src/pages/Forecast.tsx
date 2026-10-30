import { Tooltip } from "../shared/ui/Tooltip";
import { useEffect, useState } from "react";
import { Button, LinkButton } from "../shared/ui/Button";
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
  history: { period: number; value: number; period_start: string; period_end: string }[];
  forecast: { period: number; value: number; lower: number; upper: number; period_start: string; period_end: string }[];
  unused_daily_count: number;
  missing_daily_count: number;
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
    [automaticPeriod, setAutomaticPeriod] = useState(true),
    [horizon, setHorizon] = useState(36);
  const choosePeriod = (value: number, automatic = false) => {
    setPeriod(value);
    setAutomaticPeriod(automatic);
    setHorizon(value === 30 ? 36 : value === 7 ? 52 : 1095);
  };
  useEffect(() => {
    setStart("");
    setEnd("");
    choosePeriod(30, true);
  }, [p.objectId, p.aggregateId]);
  const start = startChoice || dates.data?.dates[0] || dateShift(p.day, -90),
    end = endChoice || dates.data?.dates.at(-1) || p.day;
  useEffect(() => {
    if (automaticPeriod) choosePeriod(30, true);
  }, [start, end]);
  const resource = useResource<Forecast>(
    p.objectId &&
      p.aggregateId &&
      dates.data?.dates.length &&
      start &&
      end &&
      start <= end &&
      horizon >= 1 &&
      horizon <= 3660
      ? `/objects/${segment(p.objectId)}/aggregates/${segment(p.aggregateId)}/forecast?start=${start}&end=${end}&period_days=${period}&horizon=${horizon}`
      : null,
  );
  const insufficient = Boolean(resource.error?.includes("≥3 исторических периода"));
  useEffect(() => {
    if (automaticPeriod && insufficient && period > 1)
      choosePeriod(period === 30 ? 7 : 1, true);
  }, [automaticPeriod, insufficient, period]);
  const data = resource.data;
  const displayDate = (value: string) => value.split("-").reverse().join(".");
  const allHistory = () => {
    setStart("");
    setEnd("");
  };
  return (
    <Panel
      title="Прогноз закачки НА"
      caption={`${p.aggregateId} · линейная экстраполяция измеренных объёмов`}
      help="Экстраполяция тренда — ориентир для сценария, не гидродинамическая модель пласта."
    >
      <p className="muted">Оценка по истории выбранного НА. Прогноз по скважинам из внешней CRM-модели доступен в отдельной вкладке.</p>
      <div className="page-controls">
        <Range start={start} end={end} onStart={setStart} onEnd={setEnd} />
        <label>
          Периодичность
          <select
            aria-label="Периодичность"
            value={period}
            onChange={(e) => {
              choosePeriod(Number(e.target.value));
            }}
          >
            <option value={1}>Сутки</option>
            <option value={7}>7 суток</option>
            <option value={30}>30 суток</option>
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
      {dates.data?.dates.length === 0 ? (
        <p className="notice">Для выбранного НА нет истории телеметрии. Импортируйте суточные объёмы закачки, чтобы построить прогноз.</p>
      ) : start > end ? (
        <p className="notice error">
          Начало периода должно быть не позже конца.
        </p>
      ) : insufficient ? (
        <div className="notice" role="status">
          <strong>Недостаточно истории для выбранной длины периода</strong>
          <p>Для тренда нужны минимум 3 полных периода по {period} суток с измеренными объёмами. Уменьшите длину периода или расширьте историю; отсутствующие записи не заменяются нулями.</p>
          <div className="page-controls">
            {period > 7 && <Button variant="secondary" onClick={() => choosePeriod(7)}>Использовать периоды по 7 суток</Button>}
            {period > 1 && <Button variant="secondary" onClick={() => choosePeriod(1)}>Использовать суточные периоды</Button>}
            {(startChoice || endChoice) && <Button variant="secondary" onClick={allHistory}>Вся доступная история</Button>}
          </div>
          {period === 1 && !startChoice && !endChoice && <>
            <p>В доступном архиве нет трёх суточных объёмов. Для прогноза нужно импортировать дополнительную историю.</p>
            <p>Записи мгновенного расхода не заменяют измеренные суточные объёмы закачки.</p>
            <LinkButton href="#telemetry">Проверить телеметрию</LinkButton>
          </>}
        </div>
      ) : (
        dates.data && <Status {...resource} />
      )}
      {data && (
        <>
          {automaticPeriod && period !== 30 && <p className="notice">Автоматически выбраны периоды по {period} суток: для трёх периодов по 30 суток истории недостаточно. Длину периода можно изменить выше.</p>}
          <p data-testid="forecast-calendar">История: {displayDate(data.history[0].period_start)} — {displayDate(data.history.at(-1)!.period_end)}. Прогноз: {displayDate(data.forecast[0].period_start)} — {displayDate(data.forecast.at(-1)!.period_end)} ({horizon} периодов по {period} суток).</p>
          {data.unused_daily_count > 0 && <p className="muted">Последние суточные записи ({data.unused_daily_count}) не образуют полный период и не входят в тренд.</p>}
          {data.missing_daily_count > 0 && <p className="notice">В использованной истории отсутствуют суточные записи: {data.missing_daily_count}. Периоды объединяют измеренные сутки; пропуски не считаются нулевой закачкой. Календарная длина исторического периода может отличаться от выбранной.</p>}
          <div className="page-kpis">
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
          <Plot
            title="Факт и прогноз закачки"
            data={forecastTraces(data) as Trace[]}
            layout={{
              xaxis: {
                title: { text: `Период (${period} сут); 0 — ${displayDate(data.history.at(-1)!.period_end)}` },
              },
              yaxis: { title: { text: "Объём, м³" } },
            }}
          />
          <details>
            <summary>Модель прогноза</summary>
            <p>{data.estimate ? "Сценарная оценка" : "По измерениям"}: {data.method === "linear-trend" ? "линейная экстраполяция тренда (МНК)" : data.method}</p>
            {data.note && <p className="muted">{data.note}</p>}
            <div className="page-kpis">
            <div>
              Тренд, м³/период<Tooltip label="Тренд" content="Изменение объёма за один выбранный период: сутки, неделю или месяц." /><strong>{fmt(data.trend_slope)}</strong>
            </div>
            <div>
              Базовый ориентир, м³<Tooltip label="Базовый ориентир" content="Среднее последних измеренных периодов, повторённое на будущие периоды без изменения тренда." /><strong>{fmt(data.naive_baseline, 0)}</strong>
            </div>
            </div>
          </details>
          <details>
            <summary>Таблица прогноза</summary>
            <Table
              rows={data.forecast}
              columns={[
                { key: "period", label: "Период" },
                { key: "period_start", label: "Начало", render: (row) => displayDate(String(row.period_start)) },
                { key: "period_end", label: "Конец", render: (row) => displayDate(String(row.period_end)) },
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
