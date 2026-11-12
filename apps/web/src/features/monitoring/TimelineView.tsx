import { useEffect, useMemo, useRef, useState } from "react";
import { TelemetryChart, type TelemetrySignal } from "../../pages/TelemetryChart";
import { segment, useResource } from "../../shared/api";
import { efficiencyPercent } from "../../shared/format/number.mjs";
import { Button } from "../../shared/ui/Button";
import { MetricCard } from "../../shared/ui/MetricCard";
import { Panel } from "../../shared/ui/Panel";
import { Range } from "../../shared/ui/Range";
import { Status } from "../../shared/ui/Status";
import { recentPeriod, timelineSignal, latestMetricPoint } from "./timeline.mjs";
import { TimeRangeControl } from "../../shared/ui/TimeRangeControl";
import { PeriodComparison } from "./PeriodComparison";
import "./timeline.css";

type TimelinePoint = {
  timestamp: string; sec_kwh_m3: number | null; efficiency: number | null;
  sec_calc_kwh_m3: number | null; sec_optimal_kwh_m3: number | null; nominal_efficiency: number | null;
  flow_m3h: number | null; power_kw: number | null; p_in_mpa: number | null; p_out_mpa: number | null;
  volume_m3: number | null; energy_kwh: number | null; quality: "ready" | "partial" | "missing";
  basis?: "daily" | "interval" | "none"; snapshot_timestamp: string | null;
};
type Timeline = {
  object_id: string; aggregate_id: string | null; start: string; end: string;
  interval_hours: number; basis: "daily" | "interval" | "mixed" | "none"; latest_at: string | null;
  points: TimelinePoint[]; aggregates: { code: string; role: string }[];
  observations: { title: string; detail: string; tone: "neutral" | "warn" }[]; notes: string[];
};
type Period = { start: string; end: string };
const dateLabel = (value: string) => new Date(value).toLocaleString("ru-RU", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });

export function TimelineView({ objectId, aggregateId = "", timestamp, onSelectTimestamp }: {
  objectId: string; aggregateId?: string;
  timestamp: string; onSelectTimestamp: (timestamp: string) => void;
}) {
  const [period, setPeriod] = useState<Period | null>(() => {
    const params = new URL(location.href).searchParams;
    const start = params.get("start"), end = params.get("end");
    return start && end && /^\d{4}-\d{2}-\d{2}$/.test(start) && /^\d{4}-\d{2}-\d{2}$/.test(end) ? { start, end } : null;
  });
  const objectRef = useRef(objectId);
  const [cursor, setCursor] = useState<number | null>(null);
  const [viewport, setViewport] = useState<[number, number] | null>(null);
  const followedTimestamp = useRef("");
  const baseUrl = `/objects/${segment(objectId)}/timeline${aggregateId ? `?aggregate_id=${segment(aggregateId)}` : ""}`;
  const current = useResource<Timeline>(baseUrl);
  const validPeriod = !period || Boolean(period.start && period.end && period.start <= period.end);
  const query = period && validPeriod ? `${baseUrl}${aggregateId ? "&" : "?"}start=${period.start}&end=${period.end}` : null;
  const history = useResource<Timeline>(query);
  const resource = period ? history : current;
  const data = resource.data;
  const from = period?.start ?? current.data?.start ?? "";
  const to = period?.end ?? current.data?.end ?? "";
  function changePeriod(value: Period | null) {
    setPeriod(value);
    const url = new URL(location.href);
    if (value) { url.searchParams.set("start", value.start); url.searchParams.set("end", value.end); }
    else { url.searchParams.delete("start"); url.searchParams.delete("end"); }
    window.history.replaceState(null, "", url);
  }
  useEffect(() => {
    if (objectRef.current !== objectId) { objectRef.current = objectId; changePeriod(null); }
  }, [objectId]);
  useEffect(() => { setCursor(null); setViewport(null); }, [objectId, aggregateId, from, to]);
  const charts = useMemo(() => {
    if (!data) return [];
    const hours = data.interval_hours;
    function signal(key: keyof TimelinePoint, metric: string, unit: string): TelemetrySignal {
      return { metric, unit, points: timelineSignal(data!.points, key, hours).map(point => ({ ...point, value: key === "efficiency" || key === "nominal_efficiency" ? efficiencyPercent(point.value) : point.value })) };
    }
    return [
      { title: "Удельный расход энергии", series: [
        signal("sec_kwh_m3", data.basis === "daily" ? "УРЭ факт" : "УРЭ по парным данным", "кВт·ч/м³"),
        signal("sec_calc_kwh_m3", "УРЭ расчётный", "кВт·ч/м³"),
        signal("sec_optimal_kwh_m3", "УРЭ оптим. по БГ", "кВт·ч/м³"),
      ] },
      { title: data.basis === "daily" ? "Энергия за сутки" : "Энергия за интервал", series: [signal("energy_kwh", "Энергия", "кВт·ч")] },
      data.points.some(point => point.flow_m3h != null)
        ? { title: "Расход", series: [signal("flow_m3h", "Расход", "м³/ч")] }
        : { title: data.basis === "daily" ? "Закачка за сутки" : "Закачка за интервал", series: [signal("volume_m3", "Объём закачки", "м³")] },
      { title: "Мощность", series: [signal("power_kw", "Мощность", "кВт")] },
      { title: "Давления", series: [signal("p_in_mpa", "Давление на входе", "МПа"), signal("p_out_mpa", "Давление на выходе", "МПа")] },
    ].filter(chart => chart.series.some(signal => signal.points.some(point => point.value !== null)));
  }, [data]);
  const domain = useMemo<[number, number]>(() => {
    const times = (data?.points ?? []).map(point => new Date(point.timestamp).getTime()).filter(Number.isFinite);
    if (!times.length) return [0, 1];
    const first = Math.min(...times), last = Math.max(...times);
    return first === last ? [first - 3600000, last + 3600000] : [first, last];
  }, [data]);
  const selectedTime = new Date(timestamp).getTime(), visibleRange = viewport ?? domain;
  const visibleTimestamp = selectedTime >= visibleRange[0] && selectedTime <= visibleRange[1] ? timestamp : undefined;
  const interaction = {
    cursor, onCursor: setCursor, viewport, onViewport: setViewport, domain,
    onSelectX: (value: number) => {
      const point = data?.points.find(point => new Date(point.timestamp).getTime() === value);
      if (point) onSelectTimestamp(point.timestamp);
    },
  };
  useEffect(() => {
    const value = new Date(timestamp).getTime();
    if (!data || !Number.isFinite(value) || !validPeriod || !from || !to || followedTimestamp.current === timestamp) return;
    followedTimestamp.current = timestamp;
    const selectedDay = timestamp.slice(0,10);
    if (selectedDay < from || selectedDay > to) {
      const days = Math.round((Date.parse(to) - Date.parse(from)) / 86400000) + 1;
      changePeriod(recentPeriod(timestamp, days));
    } else if (viewport && (value < viewport[0] || value > viewport[1])) {
      const width = viewport[1] - viewport[0];
      const start = Math.max(domain[0], Math.min(value - width / 2, domain[1] - width));
      setViewport([start, start + width]);
    }
  }, [timestamp, from, to, validPeriod, viewport, domain, data]);
  const basisLabels = { daily: "Суточные показатели", interval: "Измерения с интервалом 2 часа", mixed: "Смешанная детализация: суточные и интервальные данные", none: "Измерений пока нет" };
  return <div className="timeline-view">
    <Panel title="Последние показатели" action={<span className="timeline-scope" aria-label="Граница показателей">{aggregateId || "Вся станция"}</span>}>
      {period && <Status {...current} />}
      <div className="page-kpis timeline-kpis">
        {[
          { name: "УРЭ", key: "sec_kwh_m3", unit: "кВт·ч/м³" },
          { name: latestMetricPoint(current.data?.points ?? [], "energy_kwh")?.basis === "daily" ? "Энергия за сутки" : "Энергия за интервал", key: "energy_kwh", unit: "кВт·ч" },
          latestMetricPoint(current.data?.points ?? [], "flow_m3h")
            ? { name: "Расход", key: "flow_m3h", unit: "м³/ч" }
            : { name: latestMetricPoint(current.data?.points ?? [], "volume_m3")?.basis === "daily" ? "Закачка за сутки" : "Закачка за интервал", key: "volume_m3", unit: "м³" },
          { name: "Мощность", key: "power_kw", unit: "кВт" },
        ].map(metric => {
          const point = latestMetricPoint(current.data?.points ?? [], metric.key);
          const value = point?.[metric.key as keyof TimelinePoint];
          return <article className="timeline-kpi" key={metric.name} aria-label={metric.name}>
            <MetricCard label={metric.name} value={value} unit={metric.unit} help={metric.key === "sec_kwh_m3"
              ? point?.basis === "daily"
                ? "Последний суточный УРЭ: измеренная энергия / объём за те же сутки; не итог выбранного периода."
                : "Отношение мощности к расходу по парному замеру; не измеренные энергия и объём за весь период."
              : metric.name + ": последнее доступное измерение."} />
            {metric.key === "sec_kwh_m3" && point && <small>{point.basis === "daily" ? "Суточный факт" : point.basis === "interval" ? "По парным замерам" : "Временная база не указана"}</small>}
            {point && <time dateTime={point.timestamp} title="Дата измерения">{dateLabel(point.timestamp)}</time>}
          </article>;
        })}
      </div>
    </Panel>
    <Panel title="История показателей">
      <p className="muted">{basisLabels[data?.basis ?? "none"]}. Суточный УРЭ — W / Q_сут; интервальный — отношение мощности к расходу по парным замерам, не измеренные энергия и объём за период. Расчётные ориентиры относятся к исходному режиму, а не к суточному факту.</p>
      <div className="timeline-presets" aria-label="Быстрый выбор периода">
        {[7, 30, 90].map(days => <Button key={days} variant="secondary" disabled={!current.data?.latest_at} onClick={() => changePeriod(recentPeriod(current.data!.latest_at!, days))}>{days} дней</Button>)}
        <Button variant="secondary" onClick={() => changePeriod(null)}>Последние данные</Button>
      </div>
      <div className="page-controls"><Range start={from} end={to} onStart={start => changePeriod({ start, end: to })} onEnd={end => changePeriod({ start: from, end })} /></div>
      {!validPeriod ? <p className="notice error" role="alert">Укажите начало и конец периода. Начало должно быть не позже конца.</p> : <Status {...resource} />}
      {data && validPeriod && <>
        {!charts.length ? <p className="notice">За выбранный период измерений нет. Выберите другой период или вернитесь к последним данным.</p> : <>
          <TimeRangeControl domain={domain} viewport={viewport} onChange={setViewport} />
          <div className="timeline-charts">{charts.map(chart => <div key={chart.title}><TelemetryChart compact title={chart.title} series={chart.series.filter(signal => signal.points.some(point => point.value !== null))} timestamp={visibleTimestamp} timeInteraction={{ ...interaction, showBrush: false }} /></div>)}</div>
        </>}
      </>}
    </Panel>
    <PeriodComparison objectId={objectId} aggregateId={aggregateId} start={from} end={to} data={validPeriod ? data : undefined}>
      <details><summary>Данные и ограничения</summary><p>Ожидаемый интервал новой телеметрии — 2 часа. Суточные показатели не превращаются в двухчасовые измерения. Для всей станции используются суммарные показатели; КПД отдельных насосов не усредняется.</p>
        <p className="muted">{period ? "Выбранный период закреплён" : "Последний доступный период"} · {basisLabels[data?.basis ?? "none"]}. Пропуски не соединяются линией.</p>
        {(data?.notes ?? []).map((note, index) => <p className="muted" key={index}>{note}</p>)}</details>
    </PeriodComparison>
  </div>;
}
