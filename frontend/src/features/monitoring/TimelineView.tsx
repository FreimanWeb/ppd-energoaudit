import { useEffect, useMemo, useRef, useState } from "react";
import { TelemetryChart, type TelemetrySignal } from "../../pages/TelemetryChart";
import { segment, useResource } from "../../shared/api";
import { formatMetric, efficiencyPercent } from "../../shared/format/number.mjs";
import { Button } from "../../shared/ui/Button";
import { Panel } from "../../shared/ui/Panel";
import { Range } from "../../shared/ui/Range";
import { Status } from "../../shared/ui/Status";
import { Table } from "../../shared/ui/Table";
import { formatNumber } from "../../shared/format/number.mjs";
import { recentPeriod, timelineSignal, latestMetricPoint, timelineFocus, timelineComparison } from "./timeline.mjs";
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

export function TimelineView({ objectId, objectName, aggregateId = "", onAggregateChange, onInspect }: {
  objectId: string; objectName: string; aggregateId?: string;
  onAggregateChange: (code: string) => void; onInspect: (timestamp: string, page?: "snapshot" | "losses") => void;
}) {
  const [period, setPeriod] = useState<Period | null>(() => {
    const params = new URL(location.href).searchParams;
    const start = params.get("start"), end = params.get("end");
    return start && end && /^\d{4}-\d{2}-\d{2}$/.test(start) && /^\d{4}-\d{2}-\d{2}$/.test(end) ? { start, end } : null;
  });
  const objectRef = useRef(objectId);
  const [cursor, setCursor] = useState<number | null>(null);
  const [viewport, setViewport] = useState<[number, number] | null>(null);
  const [selected, setSelected] = useState<TimelinePoint | null>(null);
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
  useEffect(() => { setCursor(null); setViewport(null); setSelected(null); }, [objectId, aggregateId, from, to]);
  const charts = useMemo(() => {
    if (!data) return [];
    const hours = data.interval_hours;
    function signal(key: keyof TimelinePoint, metric: string, unit: string): TelemetrySignal {
      return { metric, unit, points: timelineSignal(data!.points, key, hours).map(point => ({ ...point, value: key === "efficiency" || key === "nominal_efficiency" ? efficiencyPercent(point.value) : point.value })) };
    }
    return [
      { title: "Удельный расход энергии", series: [
        signal("sec_kwh_m3", "УРЭ факт", "кВт·ч/м³"),
        signal("sec_calc_kwh_m3", "УРЭ расчётный", "кВт·ч/м³"),
        signal("sec_optimal_kwh_m3", "УРЭ оптимальный по БГ", "кВт·ч/м³"),
      ] },
      { title: "КПД агрегата", series: [signal("efficiency", "КПД факт", "%"), signal("nominal_efficiency", "КПД паспортный", "%")] },
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
  const interaction = {
    cursor, onCursor: setCursor, viewport, onViewport: setViewport, domain,
    onSelectX: (value: number) => setSelected(data?.points.find(point => new Date(point.timestamp).getTime() === value) ?? null),
  };
  const focus = selected ?? timelineFocus(data?.points ?? []);
  const comparison = focus ? timelineComparison(data?.points ?? [], focus.timestamp) : null;
  const basisLabels = { daily: "Суточные показатели", interval: "Измерения с интервалом 2 часа", mixed: "Смешанная детализация: суточные и интервальные данные", none: "Измерений пока нет" };
  return <div className="timeline-view">
    <Panel title="Последние показатели" caption={`${objectName} · Обзор состояния и история работы`}>
      <div className="timeline-heading">
        <div><span className="timeline-eyebrow">Последние доступные данные</span><strong>{current.data?.latest_at ? dateLabel(current.data.latest_at) : "Ожидаем телеметрию"}</strong>
          <p className="muted">{basisLabels[current.data?.basis ?? "none"]}. Значения не означают состояние в реальном времени.</p></div>
        <label>Оборудование<select aria-label="Оборудование в истории" value={aggregateId} onChange={event => onAggregateChange(event.target.value)}>
          <option value="">Вся станция</option>{current.data?.aggregates.map(aggregate => <option key={aggregate.code} value={aggregate.code}>{aggregate.code} · {aggregate.role}</option>)}
        </select></label>
      </div>
      {period && <Status {...current} />}
      <div className="page-kpis timeline-kpis">
        {[
          { name: "УРЭ", key: "sec_kwh_m3", unit: "кВт·ч/м³" },
          latestMetricPoint(current.data?.points ?? [], "efficiency")
            ? { name: "КПД", key: "efficiency", unit: "%" }
            : { name: latestMetricPoint(current.data?.points ?? [], "energy_kwh")?.basis === "daily" ? "Энергия за сутки" : "Энергия за интервал", key: "energy_kwh", unit: "кВт·ч" },
          latestMetricPoint(current.data?.points ?? [], "flow_m3h")
            ? { name: "Расход", key: "flow_m3h", unit: "м³/ч" }
            : { name: latestMetricPoint(current.data?.points ?? [], "volume_m3")?.basis === "daily" ? "Закачка за сутки" : "Закачка за интервал", key: "volume_m3", unit: "м³" },
          { name: "Мощность", key: "power_kw", unit: "кВт" },
        ].map(metric => {
          const point = latestMetricPoint(current.data?.points ?? [], metric.key);
          const value = point?.[metric.key as keyof TimelinePoint];
          return <div key={metric.name}>{metric.name}<strong>{formatMetric(metric.key === "efficiency" ? efficiencyPercent(value) : value, metric.unit)} <small>{metric.unit}</small></strong><span>{point ? dateLabel(point.timestamp) : "Нет измерений"}</span></div>;
        })}
      </div>
    </Panel>
    <Panel title="История показателей" caption="Сопоставьте начало ухудшения с изменениями расхода, мощности и давления.">
      <div className="timeline-presets" aria-label="Быстрый выбор периода">
        {[7, 30, 90].map(days => <Button key={days} variant="secondary" disabled={!current.data?.latest_at} onClick={() => changePeriod(recentPeriod(current.data!.latest_at!, days))}>{days} дней</Button>)}
        <Button variant="secondary" onClick={() => changePeriod(null)}>Последние данные</Button>
        {viewport && <Button variant="secondary" onClick={() => setViewport(null)}>Сбросить масштаб</Button>}
      </div>
      <div className="page-controls"><Range start={from} end={to} onStart={start => changePeriod({ start, end: to })} onEnd={end => changePeriod({ start: from, end })} /></div>
      <p className="timeline-period muted">{period ? "Выбранный период закреплён" : "Последний доступный период"} · {basisLabels[data?.basis ?? "none"]}. Пропуски не соединяются линией.</p>
      {data && aggregateId && <p className="muted">УРЭ: факт, расчётный при паспортном КПД и оптимальный по давлению БГ. Ориентиры меняются с режимом; суточный факт и отдельные замеры давления имеют разную временную базу.</p>}
      {data && !aggregateId && <p className="notice">Выберите агрегат, чтобы увидеть его КПД и расчётные ориентиры УРЭ. Для всей станции паспортные КПД насосов не усредняются.</p>}
      {data && aggregateId && !data.points.some(point => point.efficiency != null) && <p className="notice">Фактический КПД недоступен: нужны синхронные расход, мощность и давления. Суточный УРЭ не заменяет эти измерения; паспортный КПД показан как ориентир при наличии данных.</p>}
      {!validPeriod ? <p className="notice error" role="alert">Укажите начало и конец периода. Начало должно быть не позже конца.</p> : <Status {...resource} />}
      {data && validPeriod && <>
        {!charts.length ? <p className="notice">За выбранный период измерений нет. Выберите другой период или вернитесь к последним данным.</p> : <>
          <p className="muted">Наведите курсор для сравнения. Выберите точку кликом или клавишей Enter для подробного разбора.</p>
          <div className="timeline-charts">{charts.map((chart, index) => <div className={index === 0 ? "timeline-chart-wide" : ""} key={chart.title}><TelemetryChart title={chart.title} series={chart.series.filter(signal => signal.points.some(point => point.value !== null))} timestamp={selected?.timestamp} timeInteraction={{ ...interaction, showBrush: index === 0 }} /></div>)}</div>
        </>}
        <div className="timeline-inspect" aria-live="polite"><div><strong>{focus ? dateLabel(focus.timestamp) : "Выберите момент на графике"}</strong>
          <p className="muted">{!aggregateId ? "Для подробного разбора выберите агрегат." : focus?.snapshot_timestamp ? focus.basis === "daily" ? "Доступен подробный расчёт доступного режима за выбранные сутки." : "Доступен подробный расчёт по измерениям выбранного момента." : "Подробный режим для этого момента недоступен. Показатели истории остаются доступны на графиках."}</p></div>
          <div className="timeline-inspect-actions">
            <Button variant="secondary" disabled={!aggregateId || !focus?.snapshot_timestamp} onClick={() => { if (aggregateId && focus?.snapshot_timestamp) onInspect(focus.snapshot_timestamp); }}>Разобрать режим</Button>
            {objectId === "kns54an" && <Button disabled={!aggregateId || !focus?.snapshot_timestamp} onClick={() => { if (aggregateId && focus?.snapshot_timestamp) onInspect(focus.snapshot_timestamp, "losses"); }}>Разобрать потери по цепочке</Button>}
          </div>
        </div>
      </>}
    </Panel>
    <Panel title="Что проверить" caption="Наблюдения помогают найти возможную причину. Это гипотезы для проверки оператором.">
      {comparison && <section className="timeline-comparison" aria-label="Изменение режима">
        <h3>{comparison.change_pct > 0 ? "УРЭ вырос" : comparison.change_pct < 0 ? "УРЭ снизился" : "УРЭ без изменений"}: {formatNumber(comparison.change_pct, 1)} %</h3>
        <p className="muted">{dateLabel(comparison.before.timestamp)} → {dateLabel(comparison.after.timestamp)}. Предыдущая доступная точка той же временной базы.</p>
        <Table rows={[
          {name: "УРЭ, кВт·ч/м³", key: "sec_kwh_m3"},
          comparison.after.basis === "daily" ? {name: "Закачка за сутки, м³", key: "volume_m3"} : {name: "Расход, м³/ч", key: "flow_m3h"},
          {name: "Мощность, кВт", key: "power_kw"},
          {name: "Давление на входе, МПа", key: "p_in_mpa"},
          {name: "Давление на выходе, МПа", key: "p_out_mpa"},
        ].map(metric => ({
          name: metric.name,
          before: comparison.before[metric.key as keyof TimelinePoint],
          after: comparison.after[metric.key as keyof TimelinePoint],
        }))} columns={[{key:"name",label:"Показатель"},{key:"before",label:"Было"},{key:"after",label:"Стало"}]} />
        <p className="muted">Условия работы могли измениться. Пустое значение означает отсутствие синхронного измерения; таблица не устанавливает причину ухудшения.</p>
      </section>}
      {data?.observations.length ? <div className="timeline-observations">{data.observations.map((observation, index) => <article key={index} className={`timeline-observation ${observation.tone}`}><strong>{observation.title}</strong><p>{observation.detail}</p></article>)}</div> : <p className="muted">Пока недостаточно данных для сравнения. Графики показывают доступные измерения без автоматического заключения о причине.</p>}
      <details><summary>Данные и ограничения</summary><p>Ожидаемый интервал новой телеметрии — 2 часа. Суточные показатели не превращаются в двухчасовые измерения. Для всей станции используются суммарные показатели; КПД отдельных насосов не усредняется.</p>
        {(data?.notes ?? []).map((note, index) => <p className="muted" key={index}>{note}</p>)}</details>
    </Panel>
  </div>;
}
