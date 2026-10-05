import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { segment, useResource } from "./api";
import { Scheme } from "./Scheme";
import type {
  Aggregate,
  Audit,
  Dates,
  Plant,
  Snapshot,
  Topology,
} from "./types";
import "./style.css";

const number = (value: number | null | undefined, digits = 1) =>
  value == null || !Number.isFinite(value)
    ? "—"
    : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(
        value,
      );
const time = (timestamp: string) => timestamp.slice(11, 19);
const basisLabel: Record<string, string> = {
  pressure: "Давление",
  flow: "Расход",
  power: "Мощность",
};
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
function Icon({ name }: { name: keyof typeof iconPaths }) {
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
      <path d={iconPaths[name]} />
    </svg>
  );
}

function App() {
  const [objectChoice, setObject] = useState("");
  const [aggregateChoice, setAggregate] = useState("");
  const [dayChoice, setDay] = useState("");
  const [timestampChoice, setTimestamp] = useState("");
  const [nodeChoice, setNode] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeSection, setActiveSection] = useState("overview");
  const objects = useResource<Plant[]>("/objects");
  const object =
    objects.data?.find((o) => o.code === objectChoice) ??
    objects.data?.find((o) => !o.is_example) ??
    objects.data?.[0];
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
    aggregatePath ? `${aggregatePath}/dates` : null,
  );
  const day = dates.data?.dates.includes(dayChoice)
    ? dayChoice
    : (dates.data?.default_date ?? dates.data?.dates.at(-1) ?? "");
  const snapshots = useResource<Snapshot[]>(
    aggregatePath && day
      ? `${aggregatePath}/snapshots?day=${segment(day)}`
      : null,
  );
  const snapshot =
    snapshots.data?.find((s) => s.timestamp === timestampChoice) ??
    snapshots.data?.[0];
  const topology = useResource<Topology>(
    objectPath ? `${objectPath}/topology` : null,
  );
  const result = useResource<Audit>(
    aggregatePath && day && snapshot ? `${aggregatePath}/snapshot-audit` : null,
    snapshot
      ? JSON.stringify({ day, timestamp: snapshot.timestamp })
      : undefined,
  );
  const audit = result.data;
  const metrics = audit?.audit.metrics;
  const usable = audit && audit.quality.status !== "unfit";
  const node =
    topology.data?.nodes.find((n) => n.id === nodeChoice) ??
    topology.data?.nodes.find((n) => n.agg === aggregate?.code);
  function chooseAggregate(code: string) {
    setAggregate(code);
    setDay("");
    setTimestamp("");
  }
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
            <a
              href="#overview"
              className={activeSection === "overview" ? "active" : ""}
              aria-current={
                activeSection === "overview" ? "location" : undefined
              }
              onClick={() => {
                setActiveSection("overview");
                setSidebarOpen(false);
              }}
            >
              <Icon name="overview" />
              <span>Обзор режима</span>
            </a>
            <a
              href="#scheme"
              className={activeSection === "scheme" ? "active" : ""}
              aria-current={activeSection === "scheme" ? "location" : undefined}
              onClick={() => {
                setActiveSection("scheme");
                setSidebarOpen(false);
              }}
            >
              <Icon name="scheme" />
              <span>Схема ППД</span>
            </a>
            {usable && (
              <a
                href="#losses"
                className={activeSection === "losses" ? "active" : ""}
                aria-current={
                  activeSection === "losses" ? "location" : undefined
                }
                onClick={() => {
                  setActiveSection("losses");
                  setSidebarOpen(false);
                }}
              >
                <Icon name="losses" />
                <span>Потери энергии</span>
              </a>
            )}
            {audit && (
              <a
                href="#sources"
                className={activeSection === "sources" ? "active" : ""}
                aria-current={
                  activeSection === "sources" ? "location" : undefined
                }
                onClick={() => {
                  setActiveSection("sources");
                  setSidebarOpen(false);
                }}
              >
                <Icon name="sources" />
                <span>Источники данных</span>
              </a>
            )}
          </nav>
          <div className="sidebar-divider" />
          <div className="eyebrow sidebar-section-title">ПАРАМЕТРЫ АНАЛИЗА</div>
          <section className="selectors" aria-label="Выбор режима">
            <label>
              Объект
              <select
                aria-label="Объект"
                value={object?.code ?? ""}
                disabled={!objects.data?.length}
                onChange={(e) => {
                  setObject(e.target.value);
                  chooseAggregate("");
                  setNode("");
                }}
              >
                <option value="" disabled>
                  Выберите объект
                </option>
                {objects.data?.map((o) => (
                  <option key={o.code} value={o.code}>
                    {o.name}
                    {o.is_example ? " (пример)" : ""}
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
                onChange={(e) => {
                  chooseAggregate(e.target.value);
                  setNode("");
                }}
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
          </section>
        </div>
        <div className="sidebar-footer">
          <span className="sidebar-dot" />
          Энергоаудит системы ППД
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
            <strong>Объекты и оборудование</strong>
          </div>
        </div>
        <span className="header-tag">
          <span className="sidebar-dot" />
          {day
            ? `${day.split("-").reverse().join(".")}${snapshot ? ` · ${time(snapshot.timestamp)}` : ""}`
            : "Режим не выбран"}
        </span>
      </header>
      <main id="overview" tabIndex={-1}>
        <div className="page-heading">
          <div className="eyebrow">РАСЧЁТНЫЙ ОБЗОР</div>
          <h1>{object?.name ?? "Энергоаудит ППД"}</h1>
          <p>
            {object
              ? `${object.ngdu_name} · ${object.water_type} вода${object.is_example ? " · Демонстрационный объект" : ""}`
              : "Выберите объект для анализа оборудования и режима работы"}
          </p>
        </div>
        <Notice {...objects} />
        <Notice {...aggregates} />
        <Notice {...dates} />
        <Notice {...snapshots} />
        <Notice {...result} />
        {objects.data?.length === 0 && (
          <p className="notice">Объекты пока не добавлены.</p>
        )}
        {aggregates.data?.length === 0 && (
          <p className="notice">У объекта нет насосных агрегатов.</p>
        )}
        {dates.data?.dates.length === 0 && (
          <p className="notice">
            Для выбранного агрегата нет дат с телеметрией.
          </p>
        )}
        {snapshots.data?.length === 0 && day && (
          <p className="notice">
            За выбранную дату нет пригодных снимков режима. Исходная телеметрия
            может быть доступна, но расчёт по ней пока не выполнен.
          </p>
        )}
        {audit && (
          <>
            <div className={`quality ${audit.quality.status}`}>
              <strong>
                {audit.quality.status === "ready"
                  ? "Данные пригодны для расчёта"
                  : audit.quality.status === "assumptions"
                    ? "Расчёт с допущениями"
                    : "Данные непригодны для достоверных выводов"}
              </strong>
              <span>
                {audit.scope.daily_kpi_is_fact
                  ? "Суточные показатели по измерениям"
                  : "Суточные показатели сценарные"}
              </span>
            </div>
            {audit.quality.issues.length > 0 && (
              <ul className="warnings">
                {audit.quality.issues.map((issue, i) => (
                  <li key={`${issue.code}-${i}`}>{issue.message}</li>
                ))}
              </ul>
            )}
            <section className="kpis" aria-label="Показатели режима">
              <div className="kpi">
                <span>Мощность для расчёта</span>
                <strong>
                  {number(metrics?.p_electric_kw)} <small>кВт</small>
                </strong>
                <p>{audit.quality.basis.power}</p>
              </div>
              <div className="kpi">
                <span>Давление на выходе</span>
                <strong>
                  {number(audit.snapshot.p_out_mpa, 2)} <small>МПа</small>
                </strong>
                <p>На входе: {number(audit.snapshot.p_in_mpa, 2)} МПа</p>
              </div>
              <div className="kpi">
                <span>КПД агрегата</span>
                <strong>
                  {usable
                    ? number(
                        metrics?.eta_unit == null
                          ? null
                          : metrics.eta_unit * 100,
                      )
                    : "—"}{" "}
                  <small>%</small>
                </strong>
                <p>
                  Номинальный:{" "}
                  {number(
                    metrics?.eta_nom == null ? null : metrics.eta_nom * 100,
                  )}{" "}
                  %
                </p>
              </div>
              <div className="kpi">
                <span>Удельный расход энергии</span>
                <strong>
                  {usable ? number(metrics?.sec_fact_kwh_m3, 3) : "—"}{" "}
                  <small>кВт·ч/м³</small>
                </strong>
                <p>
                  Расчётный:{" "}
                  {usable ? number(metrics?.sec_calc_kwh_m3, 3) : "—"}
                </p>
              </div>
            </section>
            <div className="energy-caption">
              Суточная энергия: {number(audit.regime.w)} кВт·ч ·{" "}
              {audit.scope.daily_kpi_is_fact
                ? "фактический режим"
                : "сценарная оценка"}{" "}
              · расход: {usable ? number(metrics?.flow_m3h) : "—"} м³/ч
            </div>
          </>
        )}
        <section className="scheme-panel" id="scheme" tabIndex={-1}>
          <div className="section-heading">
            <div>
              <h2>Технологическая схема ППД</h2>
              <p>{topology.data?.title || "От приёма воды до пласта"}</p>
            </div>
            {topology.data && (
              <span className="tag">
                {topology.data.is_typical ? "Типовая схема" : "Схема объекта"}
              </span>
            )}
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
                {node?.type === "pump" && (
                  <>
                    {node.agg && (
                      <p>
                        Агрегат: <strong>{node.agg}</strong>
                      </p>
                    )}
                    {node.agg === aggregate?.code && audit ? (
                      <dl>
                        <dt>Давление на входе</dt>
                        <dd>{number(audit.snapshot.p_in_mpa, 2)} МПа</dd>
                        <dt>Давление на выходе</dt>
                        <dd>{number(audit.snapshot.p_out_mpa, 2)} МПа</dd>
                        <dt>Мощность в момент измерения</dt>
                        <dd>{number(audit.snapshot.power_kw)} кВт</dd>
                        <dt>Фактический напор</dt>
                        <dd>{usable ? number(metrics?.h_fact_m) : "—"} м</dd>
                      </dl>
                    ) : (
                      <p className="muted">
                        Выберите агрегат и момент измерения, чтобы увидеть его
                        показатели.
                      </p>
                    )}
                  </>
                )}
                <p className="muted sidebar-note">
                  Показатели других насосов не подменяются измерениями
                  выбранного агрегата.
                </p>
              </aside>
            </div>
          )}
          {topology.data && (
            <p className="scheme-source">
              {topology.data.is_typical
                ? "Типовая схема показывает состав энергоцепочки; расположение оборудования требуется уточнить для объекта."
                : `Источник схемы: ${topology.data.source}`}
            </p>
          )}
        </section>
        {audit && usable && (
          <section className="losses-panel" id="losses" tabIndex={-1}>
            <div className="section-heading">
              <div>
                <h2>Потери энергии</h2>
                <p>
                  Годовая оценка при{" "}
                  {number(audit.scope.annual_runtime_hours, 0)} ч работы
                  {audit.scope.annual_runtime_is_assumed
                    ? " — время работы принято как допущение"
                    : ""}
                </p>
              </div>
              <span className="tag">Сценарная оценка</span>
            </div>
            {audit.losses.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Составляющая</th>
                      <th>Мощность, кВт</th>
                      <th>Доля, %</th>
                      <th>Энергия, кВт·ч/год</th>
                      <th>Стоимость, ₽/год</th>
                    </tr>
                  </thead>
                  <tbody>
                    {audit.losses.map((loss, i) => (
                      <tr key={`${loss.name}-${i}`}>
                        <td>{loss.name}</td>
                        <td>{number(loss.power_kw)}</td>
                        <td>{number(loss.share * 100)}</td>
                        <td>{number(loss.annual_kwh, 0)}</td>
                        <td>{number(loss.annual_rub, 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="notice">
                Для этого режима состав потерь не рассчитан.
              </p>
            )}
          </section>
        )}
        {audit && (
          <details className="provenance" id="sources">
            <summary>Источники данных и допущения</summary>
            <h3>Источники</h3>
            <dl>
              {Object.entries(audit.sources).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <h3>Основание расчёта</h3>
            <dl>
              {Object.entries(audit.quality.basis).map(([key, value]) => (
                <div key={key}>
                  <dt>{basisLabel[key] ?? key}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </details>
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
    <App />
  </StrictMode>,
);
