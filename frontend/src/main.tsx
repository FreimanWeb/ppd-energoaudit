import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { segment, useResource } from "./api";
import { Auth } from "./Auth";
import { Calendar } from "./Calendar";
import { Scheme } from "./Scheme";
import {
  OverviewView,
  SnapshotView,
  SourcesView,
  LossesView,
} from "./DashboardViews";
import { pages, pageForMode, filterObjects } from "./navigation.mjs";
import { TelemetryPage } from "./pages/Telemetry";
import { ForecastPage } from "./pages/Forecast";
import { CRMPage } from "./pages/CRM";
import { CRMWellsPage } from "./pages/CRMWells";
import { WorkingPointPage } from "./pages/WorkingPoint";
import { MeasuresPage } from "./pages/Measures";
import { FormulasPage } from "./pages/Formulas";
import { OnboardingPage } from "./pages/Onboarding";
import type { PageProps } from "./pages/common";
import type {
  Aggregate,
  Audit,
  Dates,
  Plant,
  Snapshot,
  Topology,
} from "./types";
import "./style.css";

const fmt = (value: unknown, digits = 2) =>
  value == null
    ? "—"
    : typeof value === "number"
      ? new Intl.NumberFormat("ru-RU", {
          maximumFractionDigits: digits,
        }).format(value)
      : String(value);
const time = (timestamp: string) => timestamp.slice(11, 19);
function Notice({ error, loading }: { error?: string; loading?: boolean }) {
  return error ? (
    <p className="notice error" role="alert">
      {error}
    </p>
  ) : loading ? (
    <p className="notice" role="status">
      Загружаем данные…
    </p>
  ) : null;
}
const iconPaths = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  scheme: "M3 9h5v6H3z M16 3h5v6h-5z M16 15h5v6h-5z M8 12h4V6h4 M12 12v6h4",
  losses: "M4 20V10h4v10 M10 20V4h4v16 M16 20v-7h4v7 M2 20h20",
  sources: "M6 3h9l4 4v14H6z M15 3v5h4 M9 12h7 M9 16h7",
  menu: "M4 6h16 M4 12h16 M4 18h16",
};
function Icon({ name }: { name: string }) {
  return (
    <svg
      className="ui-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path
        d={iconPaths[name as keyof typeof iconPaths] || iconPaths.overview}
      />
    </svg>
  );
}
function Filters({
  title,
  options,
  chosen,
  onChange,
}: {
  title: string;
  options: string[];
  chosen: string[];
  onChange: (value: string[]) => void;
}) {
  return (
    <details className="object-filter">
      <summary>
        {title}
        <span>{chosen.length || "Все"}</span>
      </summary>
      <div>
        {options.map((value) => (
          <label key={value}>
            <input
              type="checkbox"
              aria-label={`${title}: ${value}`}
              checked={chosen.includes(value)}
              onChange={(e) =>
                onChange(
                  e.target.checked
                    ? [...chosen, value]
                    : chosen.filter((x) => x !== value),
                )
              }
            />
            {value}
          </label>
        ))}
      </div>
    </details>
  );
}
function App({ logout }: { logout?: () => void }) {
  const [objectChoice, setObject] = useState(""),
    [aggregateChoice, setAggregate] = useState(""),
    [dayChoice, setDay] = useState(""),
    [timestampChoice, setTimestamp] = useState(""),
    [nodeChoice, setNode] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false),
    [mode, setMode] = useState("analysis"),
    [rawPage, setPage] = useState(location.hash.slice(1) || "overview");
  const [waters, setWaters] = useState<string[]>([]),
    [ngdus, setNgdus] = useState<string[]>([]);
  useEffect(() => {
    const update = () => {
      setPage(location.hash.slice(1) || "overview");
      window.scrollTo({ top: 0, behavior: "instant" });
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  const page = pageForMode(mode, rawPage),
    source = mode === "field_trip" ? "field_trip" : "telemetry";
  const objects = useResource<Plant[]>("/catalog/objects");
  const filtered = filterObjects(objects.data ?? [], waters, ngdus);
  const object =
    filtered.find((o) => o.code === objectChoice) ??
    filtered.find((o) => o.code === "kns54an") ??
    filtered[0];
  const objectPath = object ? `/objects/${segment(object.code)}` : null;
  const aggregates = useResource<Aggregate[]>(
    objectPath ? `${objectPath}/aggregates` : null,
  );
  const aggregate =
    aggregates.data?.find((a) => a.code === aggregateChoice) ??
    aggregates.data?.find((a) => a.has_telemetry) ??
    aggregates.data?.[0];
  const aggregatePath =
    objectPath && aggregate
      ? `${objectPath}/aggregates/${segment(aggregate.code)}`
      : null;
  const dates = useResource<Dates>(
    aggregatePath && mode !== "field_trip" ? `${aggregatePath}/dates` : null,
  );
  const day = dates.data?.dates.includes(dayChoice)
    ? dayChoice
    : (dates.data?.default_date ?? dates.data?.dates.at(-1) ?? "");
  const snapshots = useResource<Snapshot[]>(
    aggregatePath && day && mode === "analysis"
      ? `${aggregatePath}/snapshots?day=${day}`
      : null,
  );
  const snapshot =
    snapshots.data?.find((s) => s.timestamp === timestampChoice) ??
    snapshots.data?.at(-1);
  const topology = useResource<Topology>(
    objectPath && page === "scheme" ? `${objectPath}/topology` : null,
  );
  const result = useResource<Audit>(
    mode === "field_trip" && aggregatePath
      ? `${aggregatePath}/field-trip-audit`
      : aggregatePath && snapshot && mode === "analysis"
        ? `${aggregatePath}/snapshot-audit`
        : null,
    source === "field_trip"
      ? "{}"
      : snapshot
        ? JSON.stringify({ day, timestamp: snapshot.timestamp })
        : undefined,
  );
  const audit = result.data;
  const clarifications = useResource<
    { field: string; provisional_value: number | string; reason: string }[]
  >(
    objectPath && aggregate && mode === "analysis"
      ? `${objectPath}/clarifications?aggregate_id=${segment(aggregate.code)}`
      : null,
  );
  const branchPressures = useResource<Record<string, {p_in_mpa: number; p_out_mpa: number}>>(
    objectPath && page === "scheme" && mode === "analysis" && snapshot
      ? `${objectPath}/scheme-pressures?day=${day}&timestamp=${segment(snapshot.timestamp)}`
      : null,
  );
  const node =
    topology.data?.nodes.find((n) => n.id === nodeChoice) ??
    topology.data?.nodes.find((n) => n.agg === aggregate?.code);
  const context: PageProps = {
    objectId: object?.code ?? "",
    aggregateId: aggregate?.code ?? "",
    day,
    timestamp: snapshot?.timestamp ?? "",
    source,
    audit,
  };
  const contextKey = `${object?.code}/${aggregate?.code}/${mode}`;
  function chooseAggregate(code: string) {
    setAggregate(code);
    setDay("");
    setTimestamp("");
    setNode("");
  }
  function chooseMode(value: string) {
    setMode(value);
    setDay("");
    setTimestamp("");
    location.hash = pageForMode(value, rawPage);
  }
  const blockedPage = page !== rawPage && rawPage !== "overview";
  const needAudit = [
    "overview",
    "snapshot",
    "losses",
    "sources",
    "formulas",
  ].includes(page);
  const noSnapshot =
    mode === "analysis" && snapshots.data?.length === 0 && Boolean(day);
  return (
    <div
      className={`app ${sidebarOpen ? "sidebar-open" : ""}`}
      onKeyDown={(event) => {
        if (event.key === "Escape" && sidebarOpen) {
          setSidebarOpen(false);
          document.querySelector<HTMLButtonElement>(".sidebar-toggle")?.focus();
        }
      }}
    >
      <a className="skip-link" href="#overview">
        Перейти к расчёту
      </a>
      <aside
        className="app-sidebar"
        id="app-sidebar"
        aria-label="Параметры и навигация"
      >
        <div className="sidebar-brand brand">
          <span className="brand-mark">ППД</span>
          <div>
            <strong>Энергоаудит</strong>
            <span>Цифровая платформа</span>
          </div>
        </div>
        <div className="sidebar-content">
          <nav aria-label="Разделы энергоаудита" className="sidebar-nav">
            <div className="eyebrow">РАБОЧАЯ ОБЛАСТЬ</div>
            {pages.map((item) => {
              const available = pageForMode(mode, item.id) === item.id;
              return (
                <a
                  key={item.id}
                  href={`#${item.id}`}
                  className={page === item.id ? "active" : ""}
                  aria-current={page === item.id ? "page" : undefined}
                  aria-disabled={!available}
                  title={
                    !available ? "Недоступно в выбранном режиме" : undefined
                  }
                  onClick={() => setSidebarOpen(false)}
                >
                  <Icon name={item.icon} />
                  <span>{item.label}</span>
                </a>
              );
            })}
          </nav>
          <div className="sidebar-divider" />
          <div className="eyebrow sidebar-section-title">ПАРАМЕТРЫ АНАЛИЗА</div>
          <section className="selectors" aria-label="Выбор режима">
            <label>
              Режим
              <select
                aria-label="Режим"
                value={mode}
                onChange={(e) => chooseMode(e.target.value)}
              >
                <option value="analysis">Анализ по телеметрии</option>
                <option value="field_trip">Выезд</option>
                <option value="telemetry_view">Просмотр телеметрии</option>
              </select>
            </label>
            <Filters
              title="Тип воды"
              options={[...new Set(objects.data?.map((o) => o.water_type))]}
              chosen={waters}
              onChange={setWaters}
            />
            <Filters
              title="НГДУ"
              options={[...new Set(objects.data?.map((o) => o.ngdu_name))]}
              chosen={ngdus}
              onChange={setNgdus}
            />
            <label>
              Объект
              <select
                aria-label="Объект"
                value={object?.code ?? ""}
                disabled={!objects.data?.length}
                onChange={(e) => {
                  setObject(e.target.value);
                  chooseAggregate("");
                }}
              >
                <option value="" disabled>
                  Выберите объект
                </option>
                {filtered.map((o) => (
                  <option key={o.code} value={o.code}>
                    {mode === "field_trip" ? "" : o.has_telemetry ? "● " : "○ "}
                    {o.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Агрегат
              <select
                aria-label="Агрегат"
                value={aggregate?.code ?? ""}
                disabled={!aggregates.data?.length}
                onChange={(e) => chooseAggregate(e.target.value)}
              >
                <option value="" disabled>
                  Нет агрегатов
                </option>
                {aggregates.data?.map((a) => (
                  <option key={a.code} value={a.code}>
                    {a.code}
                    {a.pump_model ? ` · ${a.pump_model}` : ""}
                  </option>
                ))}
              </select>
            </label>
            {mode !== "field_trip" && (
              <>
                <label>
                  Дата
                  <select
                    aria-label="Дата"
                    value={day}
                    disabled={!dates.data?.dates.length}
                    onChange={(e) => {
                      setDay(e.target.value);
                      setTimestamp("");
                    }}
                  >
                    <option value="" disabled>
                      Нет дат
                    </option>
                    {dates.data?.dates.map((d) => (
                      <option key={d} value={d}>
                        {d.split("-").reverse().join(".")}
                      </option>
                    ))}
                  </select>
                </label>
                {aggregatePath && day && mode === "analysis" && (
                  <Calendar
                    key={`${object?.code}/${aggregate?.code}`}
                    path={aggregatePath}
                    day={day}
                    dates={dates.data?.dates ?? []}
                    onChange={(d) => {
                      setDay(d);
                      setTimestamp("");
                    }}
                  />
                )}
              </>
            )}
            {mode === "analysis" && (
              <label>
                Момент измерения
                <select
                  aria-label="Момент измерения"
                  value={snapshot?.timestamp ?? ""}
                  disabled={!snapshots.data?.length}
                  onChange={(e) => setTimestamp(e.target.value)}
                >
                  <option value="" disabled>
                    Нет измерений
                  </option>
                  {snapshots.data?.map((s) => (
                    <option key={s.timestamp} value={s.timestamp}>
                      {time(s.timestamp)}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </section>
          {clarifications.data?.length ? (
            <details className="clarifications">
              <summary>
                Требуют уточнения ({clarifications.data.length})
              </summary>
              {clarifications.data.map((c, i) => (
                <p key={i}>
                  <strong>
                    {(
                      {
                        pump_eta_nom: "КПД насоса",
                        motor_eta_nom: "КПД ЭД",
                        t_year: "Годовая наработка",
                        transmission_eff: "КПД трансмиссии",
                      } as Record<string, string>
                    )[c.field] ?? c.field}
                  </strong>
                  : {fmt(c.provisional_value)}
                  <br />
                  {c.reason}
                </p>
              ))}
            </details>
          ) : null}
        </div>
        <div className="sidebar-footer">
          <span className="sidebar-dot" />
          Энергоаудит системы ППД
          {logout && <button onClick={logout}>Выйти</button>}
        </div>
      </aside>
      <header className="app-header">
        <div className="header-heading">
          <button
            className="sidebar-toggle"
            aria-label={
              sidebarOpen ? "Закрыть боковую панель" : "Открыть боковую панель"
            }
            aria-controls="app-sidebar"
            aria-expanded={sidebarOpen}
            onClick={() => {
              if (!sidebarOpen)
                window.scrollTo({ top: 0, behavior: "instant" });
              setSidebarOpen(!sidebarOpen);
            }}
          >
            <Icon name="menu" />
          </button>
          <div className="breadcrumbs">
            <span>Энергоаудит</span>
            <span aria-hidden="true">/</span>
            <strong>{pages.find((p) => p.id === page)?.label}</strong>
          </div>
        </div>
        <span className="header-tag">
          <span className="sidebar-dot" />
          {source === "field_trip"
            ? "Выездной замер"
            : day
              ? `${day.split("-").reverse().join(".")}${snapshot ? ` · ${time(snapshot.timestamp)}` : ""}`
              : "Режим не выбран"}
        </span>
        {logout && (
          <button className="mobile-logout" onClick={logout}>
            Выйти
          </button>
        )}
      </header>
      <main id="main-content" tabIndex={-1}>
        <div className="page-heading">
          <div className="eyebrow">
            {source === "field_trip"
              ? "ВЫЕЗДНОЙ ЭНЕРГОАУДИТ"
              : "ЭНЕРГОАУДИТ ППД"}
          </div>
          <h1>{object?.name ?? "Энергоаудит ППД"}</h1>
          <p>
            {object
              ? `${object.ngdu_name} · ${object.water_type} вода`
              : "Выберите объект для анализа оборудования и режима работы"}
          </p>
        </div>
        <Notice {...objects} />
        <Notice {...aggregates} />
        <Notice {...dates} />
        <Notice {...snapshots} />
        {mode !== "telemetry_view" && <Notice {...result} />}
        {blockedPage && (
          <p className="notice">
            Этот раздел недоступен в выбранном режиме. Для расчётов выберите
            анализ по телеметрии или выездной замер.
          </p>
        )}
        {dates.data?.dates.length === 0 && (
          <p className="notice">
            Для выбранного агрегата нет дат с телеметрией.
          </p>
        )}
        {noSnapshot && (
          <p className="notice">
            За выбранную дату нет пригодных снимков режима. Доступны исходные
            измерения без расчётных выводов.
          </p>
        )}
        {audit && page !== "overview" && (
          <div className={`quality ${audit.quality.status}`}>
            <strong>
              {audit.quality.status === "unfit"
                ? "Данные непригодны для достоверных выводов"
                : audit.quality.status === "assumptions"
                  ? "Расчёт с допущениями"
                  : "Данные пригодны для расчёта"}
            </strong>
            <span>
              {source === "field_trip" ? "Выездной замер" : "Выбранный режим"}
            </span>
          </div>
        )}
        {page === "overview" && audit && (
          <OverviewView audit={audit} context={context} />
        )}
        {page === "snapshot" && audit && <SnapshotView audit={audit} />}
        {page === "losses" && audit && <LossesView audit={audit} />}
        {page === "sources" && audit && <SourcesView audit={audit} />}
        {page === "formulas" && audit && <FormulasPage {...context} />}
        {page === "telemetry" && (
          <TelemetryPage
            key={contextKey}
            {...context}
            viewerOnly={mode === "telemetry_view"}
            availableDates={dates.data?.dates}
          />
        )}
        {page === "forecast" && <ForecastPage key={contextKey} {...context} />}
        {page === "crm" && <CRMPage key={contextKey} {...context} />}
        {page === "crm-wells" && <CRMWellsPage key={contextKey} {...context} />}
        {page === "working-point" && (
          <WorkingPointPage key={contextKey} {...context} />
        )}
        {page === "measures" && <MeasuresPage key={contextKey} {...context} />}
        {page === "onboarding" && (
          <OnboardingPage key={contextKey} {...context} />
        )}
        {page === "scheme" && (
          <section className="scheme-panel">
            <div className="section-heading">
              <div>
                <h2>Технологическая схема ППД</h2>
                <p>{topology.data?.title}</p>
              </div>
              <span className="tag">
                {topology.data?.is_typical ? "Типовая схема" : "Схема объекта"}
              </span>
            </div>
            <Notice {...topology} />
            {topology.data && (
              <div className="scheme-layout">
                <div className="scheme-canvas">
                  <Scheme
                    key={object?.code}
                    topology={topology.data}
                    aggregate={aggregate?.code ?? ""}
                    audit={audit}
                        pressures={branchPressures.data}
                    selected={node?.id ?? ""}
                    onSelect={(n) => {
                      setNode(n.id);
                      if (
                        n.agg &&
                        aggregates.data?.some((a) => a.code === n.agg) &&
                        n.agg !== aggregate?.code
                      )
                        chooseAggregate(n.agg);
                    }}
                  />
                </div>
                <aside aria-label="Выбранное оборудование">
                  <div className="eyebrow">ОБОРУДОВАНИЕ</div>
                  <h3>{node?.label || "Выберите узел"}</h3>
                  {node?.sub && <p>{node.sub}</p>}
                  {node?.hint && <p className="muted">{node.hint}</p>}
                  {node && !node.hint && <p className="muted">{({
                    valve: "дросселирование: срезается ΔP·Q; кандидат на частотное регулирование",
                    wells: "Приёмистость P–Q; ограничение по лимиту закачки",
                    reservoir: "Отклик пласта (CRM): полезная и циркулирующая закачка",
                  } as Record<string, string>)[node.type]}</p>}
                  {node?.type === "source" && audit && <dl>
                    <dt>Давление на приёме</dt><dd>{fmt(audit.regime.p_in)} МПа</dd>
                    <dt>Подача за сутки</dt><dd>{fmt(audit.regime.q_day, 0)} м³/сут</dd>
                  </dl>}
                  {node?.type === "manifold" && audit && <dl>
                    <dt>Давление БГ</dt><dd>{fmt(audit.regime.p_bg)} МПа</dd>
                    <dt>Давление на выкиде</dt><dd>{fmt(audit.regime.p_out)} МПа</dd>
                  </dl>}
                  {node?.agg === aggregate?.code && audit && (
                    <dl>
                      <dt>Давление на приёме</dt>
                      <dd>{fmt(audit.regime.p_in)} МПа</dd>
                      <dt>Давление на выкиде</dt>
                      <dd>{fmt(audit.regime.p_out)} МПа</dd>
                      <dt>Мощность в момент измерения</dt>
                      <dd>{fmt(audit.snapshot?.power_kw)} кВт</dd>
                      <dt>Мощность для расчёта</dt>
                      <dd>{fmt(audit.audit.metrics.p_electric_kw)} кВт</dd>
                      <dt>Напор</dt>
                      <dd>{fmt(audit.audit.metrics.h_fact_m)} м</dd>
                      <dt>Фактический КПД</dt>
                      <dd>{fmt(audit.audit.metrics.eta_unit, 3)} о.е.</dd>
                      <dt>Номинальный КПД</dt>
                      <dd>{fmt(audit.audit.metrics.eta_nom, 3)} о.е.</dd>
                      <dt>Оценка КПД</dt>
                      <dd>{audit.quality.status === "unfit" ? "Данные непригодны для оценки" : audit.pump_assessment.name}</dd>
                      <dt>Коэффициент загрузки двигателя</dt>
                      <dd>{fmt(audit.audit.metrics.load_factor, 3)}</dd>
                      <dt>УРЭ фактический / расчётный</dt>
                      <dd>{fmt(audit.audit.metrics.sec_fact_kwh_m3, 3)} / {fmt(audit.audit.metrics.sec_calc_kwh_m3, 3)} кВт·ч/м³</dd>
                      {audit.quality.status !== "unfit" && <>
                        <dt>Потери по КПД</dt>
                        <dd>{fmt(audit.annual_summary.efficiency_energy_kwh, 0)} кВт·ч/год</dd>
                      </>}
                    </dl>
                  )}
                  <p className="muted sidebar-note">
                    Измерения относятся только к выбранному агрегату и снимку.
                  </p>
                </aside>
              </div>
            )}
            <p className="scheme-source">{topology.data?.source}</p>
          </section>
        )}
        {needAudit &&
          !audit &&
          !result.loading &&
          !result.error &&
          !noSnapshot && (
            <p className="notice">
              Выберите дату и пригодный режим либо выездной замер для расчёта.
            </p>
          )}
        {mode === "analysis" &&
          (noSnapshot || result.error) &&
          page !== "telemetry" && (
            <TelemetryPage key={`fallback/${contextKey}`} {...context} />
          )}
      </main>
      <footer>
        Цифровой энергоаудит систем ППД · расчёт по выбранному режиму
      </footer>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Auth>{(logout) => <App logout={logout} />}</Auth>
  </StrictMode>,
);
