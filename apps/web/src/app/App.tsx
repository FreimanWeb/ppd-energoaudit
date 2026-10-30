import { useEffect, useRef, useState } from "react";
import { segment, useResource } from "../shared/api";
import { Calendar } from "../features/analysis-context/Calendar";
import { AnalysisScope } from "../features/analysis-context/AnalysisScope";
import { useWellSelection } from "../shared/wellSelection";
import { NetworkLosses } from "../features/losses/NetworkLosses";
import { StationOverview } from "../features/overview/StationOverview";
import { SnapshotView } from "../features/overview/SnapshotView";
import { SourcesView } from "../features/overview/SourcesView";
import { WellHistory } from "../features/losses/WellHistory";
import { StageLosses } from "../features/losses/StageLosses";
import { PortfolioView } from "../features/monitoring/PortfolioView";
import { TimelineView } from "../features/monitoring/TimelineView";
import {
  operatorObjects,
  navigationSections,
  pageForMode,
  readAnalysisContext,
  analysisContextURL,
  initialPage,
} from "./navigation.mjs";
import { TelemetryPage } from "../pages/Telemetry";
import { ForecastPage } from "../pages/Forecast";
import { CRMPage } from "../pages/CRM";
import { CRMWellsPage } from "../pages/CRMWells";
import { WorkingPointPage } from "../pages/WorkingPoint";
import { MeasuresPage } from "../pages/Measures";
import { NetworkPage } from "../pages/Network";
import { FormulasPage } from "../pages/Formulas";
import { OnboardingPage } from "../pages/Onboarding";
import type { PageProps } from "../shared/ui/context";
import type {
  Aggregate,
  Audit,
  Dates,
  Plant,
  Snapshot,
  Topology,
} from "../shared/types";
import { Notice } from "./components/Notice";
import { Icon } from "./components/Icon";
import "../style.css";


const time = (timestamp: string) => timestamp.slice(11, 19);

export function App({ logout }: { logout?: () => void }) {
  const selectedWell = useWellSelection();
  const [selection, setSelection] = useState(() => readAnalysisContext(location.href));
  const {
    object: objectChoice,
    aggregate: aggregateChoice,
    day: dayChoice,
    timestamp: timestampChoice,
    mode,
  } = selection;
  const [sidebarOpen, setSidebarOpen] = useState(false),
    [rawPage, setPage] = useState(() => initialPage(location.href));
  useEffect(() => {
    const update = () => {
      setPage(initialPage(location.href));
      setSelection(readAnalysisContext(location.href));

      window.scrollTo({ top: 0, behavior: "instant" });
    };
    window.addEventListener("hashchange", update);
    window.addEventListener("popstate", update);
    return () => {
      window.removeEventListener("hashchange", update);
      window.removeEventListener("popstate", update);
    };
  }, []);
  const page = pageForMode(mode, rawPage),
    source = mode === "field_trip" ? "field_trip" : "telemetry";
  const monitoringPage = page === "portfolio" || page === "timeline" || page === "overview";
  const objectOnlyPage = ["well-history","crm-wells","network"].includes(page);
  const auditPage = ["snapshot","losses","network-scenario","machine-block","machine-losses","pipelines","wells","sources","formulas","working-point","measures","onboarding"].includes(page);
  const snapshotPage = auditPage || page === "telemetry" || page === "timeline";
  const objects = useResource<Plant[]>("/catalog/objects");
  const visibleObjects = operatorObjects(objects.data ?? []);
  const object =
    visibleObjects.find((o) => o.code === objectChoice) ??
    visibleObjects.find((o) => o.code === "kns54an") ??
    visibleObjects[0];
  useEffect(() => {
    if (objects.data && object && ((objectChoice && !visibleObjects.some(item => item.code === objectChoice)) || (page === "timeline" && objectChoice !== object.code))) {
      changeSelection({object:object.code,aggregate:"",day:"",timestamp:""});
    }
  }, [objects.data,objectChoice,object?.code,page]);
  const objectPath = object ? `/objects/${segment(object.code)}` : null;
  const aggregates = useResource<Aggregate[]>(
    objectPath && page !== "portfolio" && !objectOnlyPage ? `${objectPath}/aggregates` : null,
  );
  const aggregate = objectOnlyPage || page === "overview" || page === "timeline" && !aggregateChoice ? undefined :
    aggregates.data?.find((a) => a.code === aggregateChoice) ??
    aggregates.data?.find((a) => a.has_telemetry) ??
    aggregates.data?.[0];
  const aggregatePath =
    objectPath && aggregate
      ? `${objectPath}/aggregates/${segment(aggregate.code)}`
      : null;
  const dates = useResource<Dates>(
    aggregatePath && (!monitoringPage || page === "timeline") && mode !== "field_trip" ? `${aggregatePath}/dates` : null,
  );
  const stationTimes = useResource<{latest_at: string | null; points: {timestamp: string; quality: string}[]}>(
    objectPath && page === "timeline" && !aggregateChoice
      ? `${objectPath}/timeline${dayChoice ? `?start=${dayChoice}&end=${dayChoice}` : ""}` : null,
  );
  const day = dayChoice || dates.data?.default_date || dates.data?.dates.at(-1) || stationTimes.data?.latest_at?.slice(0,10) || "";
  const snapshots = useResource<Snapshot[]>(
    aggregatePath && day && snapshotPage && (!monitoringPage || page === "timeline") && mode === "analysis"
      ? `${aggregatePath}/snapshots?day=${day}`
      : null,
  );
  const snapshot = timestampChoice
    ? snapshots.data?.find((s) => s.timestamp === timestampChoice)
    : snapshots.data?.at(-1);
  const moments = page === "timeline" && !aggregateChoice
    ? stationTimes.data?.points.filter(point => point.timestamp.startsWith(day) && point.quality !== "missing")
    : snapshots.data;
  const timestamp = timestampChoice || moments?.at(-1)?.timestamp || "";
  const topology = useResource<Topology>(
    objectPath && page === "overview" ? `${objectPath}/topology` : null,
  );
  const result = useResource<Audit>(
    auditPage && mode === "field_trip" && aggregatePath
      ? `${aggregatePath}/field-trip-audit`
      : auditPage && aggregatePath && snapshot && mode === "analysis"
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
    objectPath && aggregate && auditPage && mode === "analysis"
      ? `${objectPath}/clarifications?aggregate_id=${segment(aggregate.code)}`
      : null,
  );
  const context: PageProps = {
    objectId: object?.code ?? "",
    aggregateId: aggregate?.code ?? "",
    day,
    timestamp: snapshot?.timestamp ?? "",
    source,
    audit,
    inspectionKey: new URL(location.href).searchParams.get("inspect") ?? "",
  };
  const contextKey = `${object?.code}/${aggregate?.code}/${mode}`;
  const telemetryRequest = useRef(0);
  const [telemetryMessage, setTelemetryMessage] = useState("");
  useEffect(() => { telemetryRequest.current += 1; setTelemetryMessage(""); }, [object?.code, aggregate?.code, aggregateChoice, day, mode, page]);
  async function selectTelemetryTimestamp(value: string, targetPage: "snapshot" | "losses" = "snapshot") {
    const selectedAggregate = monitoringPage ? aggregateChoice : aggregate?.code;
    if (mode !== "analysis" || !objectPath || !selectedAggregate) return;
    const selectedPath = `${objectPath}/aggregates/${segment(selectedAggregate)}`;
    const request = ++telemetryRequest.current;
    const selectedDay = value.slice(0, 10);
    setTelemetryMessage("Проверяем доступность снимка…");
    try {
      let available = selectedDay === day ? snapshots.data : undefined;
      if (!available) {
        const response = await fetch(`/api${selectedPath}/snapshots?day=${encodeURIComponent(selectedDay)}`);
        if (!response.ok) throw new Error("snapshot lookup failed");
        available = await response.json() as Snapshot[];
      }
      if (request !== telemetryRequest.current) return;
      if (!available?.some(item => item.timestamp === value)) {
        setTelemetryMessage("На выбранное время нет пригодного снимка. Текущий расчёт сохранён.");
        return;
      }
      setTelemetryMessage("");
      const next = {object: object!.code, aggregate: selectedAggregate, mode, day: selectedDay, timestamp: value};
      const url = new URL(analysisContextURL(location.href, next));
      url.hash = targetPage;
      history.pushState(null, "", url);
      setSelection(next);
      setPage(targetPage);
      window.scrollTo({top: 0, behavior: "instant"});
    } catch {
      if (request === telemetryRequest.current) setTelemetryMessage("Не удалось проверить снимок. Текущий расчёт сохранён; повторите выбор.");
    }
  }
  function changeSelection(patch: Partial<typeof selection>) {
    const next = {
      object: object?.code ?? objectChoice,
      aggregate: aggregate?.code ?? aggregateChoice,
      day,
      timestamp,
      mode,
      ...patch,
    };
    const url = new URL(analysisContextURL(location.href, next));
    if (patch.object && patch.object !== object?.code) {
      for (const key of ["well","measure","stage","inspect","network_scenario","start","end","base_start","base_end"]) url.searchParams.delete(key);
    }
    history.replaceState(null, "", url);
    if (patch.object && patch.object !== object?.code) window.dispatchEvent(new Event("ppd:well-selection"));
    setSelection(next);
  }
  function chooseAggregate(code: string) {
    changeSelection(page === "timeline" ? {aggregate:code,day:"",timestamp:""} : {aggregate: code});

  }
  function openObject(code: string) {
    const next = {object: code, aggregate: "", day: "", timestamp: "", mode: "analysis"};
    const url = new URL(analysisContextURL(location.href, next));
    for (const key of ["start", "end", "base_start", "base_end", "inspect", "well", "measure", "stage", "network_scenario"]) url.searchParams.delete(key);
    url.hash = "timeline";
    history.pushState(null, "", url);
    window.dispatchEvent(new Event("ppd:well-selection"));
    setSelection(next);
    setPage("timeline");

    setSidebarOpen(false);
    window.scrollTo({top: 0, behavior: "instant"});
  }
  function chooseDay(value: string) {
    changeSelection({day: value, timestamp: ""});
  }
  function chooseMode(value: string) {
    changeSelection({mode: value, day: "", timestamp: ""});
    location.hash = pageForMode(value, rawPage);
  }
  useEffect(() => {
    if (monitoringPage || objectOnlyPage || page === "forecast") return;
    // Пользователь или history могли изменить URL после render этого effect.
    const current = readAnalysisContext(location.href);
    if (Object.entries(selection).some(([key, value]) => current[key as keyof typeof current] !== value)) return;
    // Не заменять входящие параметры defaults, пока загружается их цепочка данных.
    if (!object || !aggregate ||
        (mode !== "field_trip" && !dates.data) ||
        (mode === "analysis" && day && !snapshots.data)) return;
    const next = {
      object: object.code,
      aggregate: aggregate.code,
      day: mode === "field_trip" ? "" : day,
      timestamp: mode === "analysis" ? timestamp : "",
      mode,
    };
    const href = analysisContextURL(location.href, next);
    if (href !== location.href) {
      history.replaceState(null, "", href);
      setSelection(next);
    }
  }, [monitoringPage, objectOnlyPage, page, object?.code, aggregate?.code, mode, day, timestamp, dates.data, snapshots.data, selection]);
  const section = navigationSections.find(group => group.pages.some(item => item.id === page));
  function navigationHref(target: string) {
    if ((target === "timeline" && mode !== "analysis") || pageForMode(mode,target) !== target) {
      const url = new URL(location.href);
      url.searchParams.set("mode","analysis");
      url.hash = target;
      return `${url.pathname}${url.search}${url.hash}`;
    }
    return `#${target}`;
  }
  const blockedPage = page !== rawPage && rawPage !== "overview";
  const needAudit = auditPage;
  const noSnapshot =
    mode === "analysis" && snapshots.data?.length === 0 && Boolean(day);
  const missingSnapshot = mode === "analysis" && Boolean(timestampChoice) && Boolean(snapshots.data?.length) && !snapshot;
  return (
    <div
      className={`app ${page === "portfolio" ? "app-portfolio" : ""} ${sidebarOpen ? "sidebar-open" : ""}`}
      onKeyDown={(event) => {
        if (event.key === "Escape" && sidebarOpen) {
          setSidebarOpen(false);
          document.querySelector<HTMLButtonElement>(".sidebar-toggle")?.focus();
        }
      }}
    >
      <a className="skip-link" href="#main-content" onClick={event => {event.preventDefault(); document.getElementById("main-content")?.focus();}}>
        Перейти к содержимому
      </a>
      {page !== "portfolio" && <aside
        className="app-sidebar"
        id="app-sidebar"
        aria-label="Параметры и навигация"
      >
        <a className="sidebar-brand brand" href="#portfolio" aria-label="Перейти ко всем объектам" onClick={() => setSidebarOpen(false)}>
          <span className="brand-mark">ППД</span>
          <div>
            <strong>Энергоаудит</strong>
            <span>Цифровая платформа</span>
          </div>
        </a>
        <div className="sidebar-content">
          <nav aria-label="Разделы энергоаудита" className="sidebar-nav">
            {navigationSections.map(section => {
              const root = section.pages.find(item => item.id === section.root)!;
              const active = section.pages.some(item => item.id === page);
              return <a key={section.root} href={navigationHref(section.root)} className={active ? "active" : ""} aria-current={active ? "page" : undefined} onClick={() => setSidebarOpen(false)}>
                <Icon name={root.icon} /><span>{section.label}</span>
              </a>;
            })}
          </nav>
          <div className="sidebar-divider" />
          {page !== "portfolio" && <details className="analysis-panel" open>
            <summary className="eyebrow sidebar-section-title">ПАРАМЕТРЫ АНАЛИЗА</summary>
            <section className="selectors" aria-label="Выбор режима">
              {!objectOnlyPage && <label>
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
              </label>}
              <label>
                Объект
                <select
                  aria-label="Объект"
                  value={object?.code ?? ""}
                  disabled={!visibleObjects.length}
                  onChange={(e) => {
                    changeSelection({object: e.target.value, aggregate: "", day: "", timestamp: ""});

                  }}
                >
                  <option value="" disabled>
                    {objects.data?.length && !visibleObjects.length ? "Нет подходящих объектов" : "Выберите объект"}
                  </option>
                  {visibleObjects.map((o) => (
                    <option key={o.code} value={o.code}>
                      {mode === "field_trip" ? "" : o.has_telemetry ? "● " : "○ "}
                      {o.name}
                    </option>
                  ))}
                </select>
              </label>
              {page !== "overview" && !objectOnlyPage && <label>
                Агрегат
                <select
                  aria-label="Агрегат"
                  value={page === "timeline" ? aggregateChoice : aggregate?.code ?? ""}
                  disabled={!aggregates.data?.length}
                  onChange={(e) => chooseAggregate(e.target.value)}
                >
                  {(page === "timeline" || !aggregates.data?.length) && <option value="" disabled={page !== "timeline"}>
                    {page === "timeline" ? "Вся станция" : aggregates.loading ? "Загрузка…" : "Нет агрегатов"}
                  </option>}
                  {aggregates.data?.map((a) => (
                    <option key={a.code} value={a.code}>
                      {a.code}
                      {a.pump_model ? ` · ${a.pump_model}` : ""}
                    </option>
                  ))}
                </select>
              </label>}
              {mode !== "field_trip" && snapshotPage && (!monitoringPage || page === "timeline") && (
                <div className="selector-time">
                  <Calendar key={`${object?.code}/${aggregate?.code}`}
                    path={aggregatePath ?? ""} day={day}
                    dates={page === "timeline" && !aggregateChoice ? undefined : dates.data?.dates ?? []}
                    max={new Date().toLocaleDateString("sv-SE")}
                    onChange={chooseDay} />
                  {mode === "analysis" && <label>
                    Момент измерения
                    <select aria-label="Момент измерения" value={timestamp} disabled={!moments?.length}
                      onChange={(e) => changeSelection({timestamp: e.target.value})}>
                      <option value="" disabled>Нет измерений</option>
                      {timestamp && !moments?.some(item => item.timestamp === timestamp) && <option value={timestamp} disabled>{time(timestamp)}</option>}
                      {moments?.map(s => <option key={s.timestamp} value={s.timestamp}>{time(s.timestamp)}</option>)}
                    </select>
                  </label>}
                </div>
              )}
            </section>
          </details>}

        </div>
        {logout && <div className="sidebar-footer sidebar-session"><button onClick={logout}>Выйти</button></div>}
      </aside>}
      {page !== "portfolio" && <button
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
      </button>}
      <main id="main-content" tabIndex={-1}>
        {page === "portfolio" && logout && <div className="portfolio-session"><button onClick={logout}>Выйти</button></div>}
        {page !== "portfolio" && <div className="page-heading">
          <h1>{object?.name ?? "Энергоаудит ППД"}</h1>
          <p>
            {object
              ? `${object.ngdu_name} · ${object.water_type} вода`
              : "Выберите объект для анализа оборудования и режима работы"}
          </p>
        </div>}
        {page !== "portfolio" && section && section.pages.length > 1 && <nav className="page-tabs" aria-label={`Вкладки: ${section.label}`}>
          {section.pages.filter(item=>!item.hidden).map(item => <a key={item.id} href={navigationHref(item.id)} aria-current={page === item.id ? "page" : undefined}>{item.label}</a>)}
        </nav>}
        {page !== "portfolio" && <AnalysisScope page={page} aggregate={page === "timeline" ? aggregateChoice : aggregate?.code ?? ""} source={source} timestamp={timestamp} well={selectedWell} />}
        {page === "portfolio" && (objects.data ? <PortfolioView onOpenObject={openObject} /> : <Notice {...objects} />)}
        {page === "timeline" && object && <TimelineView key={object.code} objectId={object.code} aggregateId={aggregateChoice} timestamp={timestampChoice || (dayChoice ? timestamp : "")}
          onSelectTimestamp={value => changeSelection({day:value.slice(0,10),timestamp:value})} />}
        {page === "timeline" && telemetryMessage && <p className="notice" role="status">{telemetryMessage}</p>}
        <Notice {...objects} />
        {page !== "portfolio" && objects.data && !visibleObjects.length && <div className="notice" role="status">
          <p>Каталог объектов пуст.</p>
        </div>}
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
        {missingSnapshot && <p className="notice">
          На выбранное время нет пригодного снимка этого агрегата. Дата и время сохранены;
          выберите другое время или другой агрегат для расчёта.
        </p>}
        {audit?.tariff_warning && <p className="notice" role="status">{audit.tariff_warning}</p>}
        {auditPage && audit && audit.quality.status !== "ready" && page !== "snapshot" && page !== "machine-block" && (
          <div className={`quality ${audit.quality.status}`}>
            <strong>
              {audit.quality.status === "unfit"
                ? "Данные непригодны для достоверных выводов"
                : "Расчёт с допущениями"}
            </strong>
            <span>
              {aggregate?.code} · {source === "field_trip" ? "Выездной замер" : "Выбранный режим"}
            </span>
          </div>
        )}
        {page === "overview" && object && <StationOverview key={`${object.code}:${source}`} objectId={object.code} source={source} topology={topology.data} />}
        {page === "snapshot" && audit && <SnapshotView audit={audit} />}
        {audit && ["machine-block","machine-losses","pipelines","wells"].includes(page) && <StageLosses key={`${audit.audit.object_id}:${audit.audit.aggregate_id}:${audit.snapshot?.timestamp ?? audit.source}:${page}`} view={page === "machine-losses" ? "map" : "indicators"} stage={page === "machine-block" || page === "machine-losses" ? "hall" : page === "pipelines" ? "pipes" : "wells"} audit={audit} inspectionKey={context.inspectionKey} />}
        {page === "well-history" && object && <WellHistory objectId={object.code} />}
        {(page === "losses" || page === "network-scenario") && audit && <NetworkLosses key={`${contextKey}:${timestamp}:${page}`} audit={audit} view={page === "losses" ? "map" : "scenario"} />}
        {(page === "losses" || page === "network-scenario") && !audit && <p className="notice">Для расчёта выберите агрегат и доступный режим.</p>}
        {page === "sources" && audit && <SourcesView audit={audit} inspectionKey={context.inspectionKey} />}
        {page === "formulas" && audit && <FormulasPage {...context} />}
        {page === "telemetry" && telemetryMessage && <p className="notice" role="status">{telemetryMessage}</p>}
        {page === "telemetry" && (
          <TelemetryPage
            key={contextKey}
            {...context}
            viewerOnly={mode === "telemetry_view"}
            availableDates={dates.data?.dates}
            onSelectTimestamp={mode === "analysis" ? selectTelemetryTimestamp : undefined}
          />
        )}
        {page === "forecast" && <ForecastPage key={contextKey} {...context} />}
        {page === "crm" && <CRMPage key={contextKey} {...context} />}
        {page === "crm-wells" && <CRMWellsPage key={contextKey} {...context} />}
        {page === "working-point" && (
          <WorkingPointPage key={contextKey} {...context} />
        )}
        {page === "measures" && <MeasuresPage key={contextKey} {...context} />}
        {page === "network" && <NetworkPage key={contextKey} {...context} />}
        {page === "onboarding" && (
          <OnboardingPage key={contextKey} {...context} />
        )}
        {needAudit &&
          !audit &&
          !result.loading &&
          !result.error &&
          !noSnapshot && !missingSnapshot && (
            <p className="notice">
              Выберите дату и пригодный режим либо выездной замер для расчёта.
            </p>
          )}
        {auditPage && mode === "analysis" &&
          (noSnapshot || missingSnapshot || result.error) &&
          page !== "telemetry" && (
            <TelemetryPage key={`fallback/${contextKey}`} {...context} />
          )}
      </main>
    </div>
  );
}
