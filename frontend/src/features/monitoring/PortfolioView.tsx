import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ParentSize } from "@visx/responsive";
import { ChartTooltip } from "../../charts/ChartTooltip";
import "../../charts/charts.css";
import { operatorObjects } from "../../app/navigation.mjs";
import { Filters } from "../../app/components/Filters";
import { Notice } from "../../app/components/Notice";
import { Calendar } from "../analysis-context/Calendar";
import { useResource } from "../../shared/api";
import { formatNumber } from "../../shared/format/number.mjs";
import { nearestSparklinePoint, portfolioHistory, sparklinePoints, visibleObjects } from "./portfolio.mjs";
import "./portfolio.css";

type MonitoringObject = {
  code: string; name: string; ngdu_name: string; water_type: string;
  status: "attention" | "normal" | "unknown";
  data_status: "fresh" | "stale" | "missing";
  latest_at: string | null; kpi_at?: string | null; basis: "daily" | "interval" | "none";
  sec_kwh_m3: number | null; efficiency: number | null; change_pct: number | null;
  history: { timestamp: string; value: number | null }[]; note: string;
};
type Portfolio = { generated_at: string; interval_hours: number; objects: MonitoringObject[] };
const statusLabel = { attention: "Требует внимания", normal: "Без сигнала", unknown: "Недостаточно данных" };
const freshnessLabel = { fresh: "Данные актуальны", stale: "Данные устарели", missing: "Нет измерений" };
const dateFormat = new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
const timestamp = (value: string) => dateFormat.format(new Date(value));
const periodDate = (value: string) => new Date(`${value}T00:00:00`).toLocaleDateString("ru-RU");

function Sparkline({ history, start, end }: { history: MonitoringObject["history"]; start: string; end: string }) {
  const [active, setActive] = useState<{index: number; anchor: DOMRect} | null>(null);
  const tooltip = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({left: 0, top: 0});
  useEffect(() => setActive(null), [history]);
  useLayoutEffect(() => {
    if (!active || !tooltip.current) return;
    const bounds = tooltip.current.getBoundingClientRect();
    const left = Math.max(12, Math.min(active.anchor.left - bounds.width / 2, window.innerWidth - bounds.width - 12));
    const above = active.anchor.top - bounds.height - 10;
    const top = above >= 12 ? above : Math.max(12, Math.min(active.anchor.bottom + 10, window.innerHeight - bounds.height - 12));
    setPosition({left, top});
  }, [active]);
  useEffect(() => {
    if (active === null) return;
    const close = () => setActive(null);
    const dismiss = (event: KeyboardEvent) => { if (event.key === "Escape") setActive(null); };
    document.addEventListener("keydown", dismiss);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("keydown", dismiss);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [active]);
  if (!sparklinePoints(history).some(Boolean)) return <div className="portfolio-no-history">Нет измерений за выбранный период</div>;
  const sample = active ? history[active.index] : null;
  return <><div className="portfolio-sparkline-frame"><ParentSize debounceTime={0}>
    {({ width, height }) => {
      if (!width || !height) return null;
      const points = sparklinePoints(history, width, height, {start, end});
      return <svg className="portfolio-sparkline" width={width} height={height} role="group" aria-label="История удельного расхода электроэнергии"
        onMouseMove={event => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const index = nearestSparklinePoint(points, event.clientX - bounds.left);
          const point = index === null ? null : points[index];
          if (index === null || !point) { setActive(null); return; }
          setActive(current => current?.index === index ? current : {
            index, anchor: new DOMRect(bounds.left + point.x - 2.5, bounds.top + point.y - 2.5, 5, 5),
          });
        }}
        onMouseLeave={() => setActive(null)}>
        <line x1="8" y1={height * 55 / 64} x2={width - 8} y2={height * 55 / 64} className="portfolio-sparkline-baseline" />
        {points.map((point, index) => point && <g key={index}>
          {points[index - 1] && <line x1={points[index - 1]!.x} y1={points[index - 1]!.y} x2={point.x} y2={point.y} />}
          <circle cx={point.x} cy={point.y} r="2.5" role="img"
            aria-label={`${timestamp(history[index].timestamp)}: ${formatNumber(history[index].value, 3)} кВт·ч/м³`} />
        </g>)}
      </svg>;
    }}
  </ParentSize></div>
  {sample?.value != null && createPortal(<div ref={tooltip} className="portfolio-point-tooltip" style={position}>
    <ChartTooltip title={timestamp(sample.timestamp)} rows={[{value: sample.value, unit: "кВт·ч/м³"}]} />
  </div>, document.body)}
  </>;
}

export function PortfolioView({ onOpenObject }: { onOpenObject: (code: string) => void }) {
  const today = new Intl.DateTimeFormat("sv-SE", {timeZone: "Europe/Moscow"}).format(new Date());
  const [endDate, setEndDate] = useState(today);
  const resource = useResource<Portfolio>(`/monitoring/objects?history_days=180&history_end=${endDate}`);
  const [query, setQuery] = useState("");
  const [ngdu, setNgdu] = useState<string[]>([]);
  const [water, setWater] = useState<string[]>([]);
  const [status, setStatus] = useState("all");
  const [historyDays, setHistoryDays] = useState(30);
  const objects = operatorObjects(resource.data?.objects ?? []);
  const visible = visibleObjects(objects, query, ngdu, water, status);
  return <div className="portfolio-page">
    <header className="portfolio-heading">
      <div><p className="portfolio-eyebrow">Мониторинг ППД</p><h1>Состояние объектов</h1><p>Найдите ухудшение, откройте историю и проверьте причину.</p></div>
      <div className="portfolio-cadence"><strong>Каждые 2 часа</strong><span>Ожидаемый интервал измерений</span></div>
    </header>
    <Notice loading={resource.loading} error={resource.error} />
    {resource.data && <div className="portfolio-summary" aria-label="Сводка по объектам">
        <div><strong>{objects.length}</strong><span>Всего объектов</span></div>
        <div className="portfolio-attention"><strong>{objects.filter(o => o.status === "attention").length}</strong><span>Требуют внимания</span></div>
        <div><strong>{objects.filter(o => o.status === "normal").length}</strong><span>Без сигнала роста УРЭ</span></div>
        <div><strong>{objects.filter(o => o.status === "unknown").length}</strong><span>Недостаточно данных</span></div>
      </div>}
      <div className="portfolio-toolbar">
        <label className="portfolio-search"><span>Поиск объекта</span><input type="search" placeholder="Название, код или НГДУ" value={query} onChange={event => setQuery(event.target.value)} /></label>
        <Filters title="НГДУ" options={[...new Set(objects.map(o => o.ngdu_name))].sort()} chosen={ngdu} onChange={setNgdu} />
        <Filters title="Тип воды" options={[...new Set(objects.map(o => o.water_type))].sort()} chosen={water} onChange={setWater} />
        <label className="portfolio-status-filter"><span>Состояние</span><select value={status} onChange={event => setStatus(event.target.value)}><option value="all">Все состояния</option>{Object.entries(statusLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="portfolio-status-filter"><span>Период графиков</span><select value={historyDays} onChange={event => setHistoryDays(Number(event.target.value))}><option value="1">Сутки</option><option value="7">Неделя · 7 дней</option><option value="30">Месяц · 30 дней</option><option value="90">3 месяца · 90 дней</option><option value="180">6 месяцев · 180 дней</option></select></label>
        <Calendar label="Дата окончания графиков" day={endDate} max={today} onChange={setEndDate} />
      </div>
      <p className="portfolio-period-note">Все графики заканчиваются выбранной датой. Участки без измерений остаются пустыми.</p>
    {resource.data && <>
      <div className="portfolio-list-heading"><span role="status">Показано {visible.length} из {objects.length}</span><span>Сначала объекты, требующие внимания</span></div>
      {!visible.length && <p className="notice">{objects.length ? "Объекты не найдены. Измените условия поиска." : "Объекты ещё не добавлены. После загрузки каталога они появятся здесь."}</p>}
      <div className="portfolio-grid">
        {visible.map(object => {
          const period = portfolioHistory(object.history, endDate, historyDays);
          return <article className={`portfolio-card portfolio-card-${object.status}`} key={object.code}>
          <div className="portfolio-card-heading"><div><p>{object.ngdu_name || "НГДУ не указано"}</p><h2>{object.name}</h2></div><span className={`portfolio-badge portfolio-badge-${object.status}`}>{statusLabel[object.status]}</span></div>
          {object.code === "demo-ppd" && <p className="notice">Демо · синтетические данные</p>}
          <p className="portfolio-object-meta">{object.code} · {object.water_type || "Тип воды не указан"}</p>
          <div className="portfolio-reading"><div><span>Удельный расход энергии</span><strong>{formatNumber(object.sec_kwh_m3, 3)} <small>кВт·ч/м³</small></strong>{object.kpi_at && <span>УРЭ за <time dateTime={object.kpi_at}>{timestamp(object.kpi_at)}</time></span>}</div><div className={`portfolio-change ${object.change_pct != null && object.change_pct > 0 ? "portfolio-change-up" : ""}`}>
            {object.change_pct == null ? <span>Нет сравнения</span> : <><strong>{object.change_pct > 0 ? "+" : ""}{formatNumber(object.change_pct, 1)} %</strong><span>к предыдущей точке той же базы</span></>}
          </div></div>
          <Sparkline history={period.history} start={period.start} end={period.end} />
          <div className="portfolio-history-caption"><span>История УРЭ</span><span>{object.basis === "daily" ? "Суточные данные" : object.basis === "interval" ? "Интервальные данные" : "Нет расчётной базы"}</span></div>
          {period.start && <div className="portfolio-history-range"><time dateTime={period.start}>{periodDate(period.start)}</time><span>—</span><time dateTime={period.end}>{periodDate(period.end)}</time></div>}
          <p className="portfolio-card-note">{object.note || "Откройте историю, чтобы сопоставить показатели объекта."}</p>
          <div className={`portfolio-freshness portfolio-freshness-${object.data_status}`}><span>{freshnessLabel[object.data_status]}</span>{object.latest_at && <span>Последние измерения: <time dateTime={object.latest_at}>{timestamp(object.latest_at)}</time></span>}</div>
          <button className="portfolio-open" onClick={() => onOpenObject(object.code)} aria-label={`Открыть историю: ${object.name}`}>Открыть историю <span aria-hidden="true">→</span></button>
        </article>; })}
      </div>
      <p className="portfolio-footnote">Порог прототипа: «Требует внимания» при росте УРЭ более 10% относительно предыдущей точки той же суточной или интервальной базы. Условия работы могут различаться и требуют проверки. Устаревшие данные не описывают текущий режим. Сводка сформирована {timestamp(resource.data.generated_at)}.</p>
    </>}
  </div>;
}
