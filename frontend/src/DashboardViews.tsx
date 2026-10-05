import { segment, useResource } from "./api";
import type { Audit } from "./types";
import { dashboardData } from "./dashboardData.mjs";
import { EfficiencyCharts, LossCharts } from "./pages/LossCharts";
import {
  Panel,
  Table,
  Status,
  fmt,
  contextBody,
  type PageProps,
} from "./pages/common";

type ViewProps = { audit: Audit };
const dictionaryColumns = [
  { key: "parameter", label: "Параметр" },
  { key: "value", label: "Значение" },
];
const basisLabel: Record<string, string> = {
  pressure: "Давление",
  flow: "Подача",
  power: "Мощность",
};
const dictionaryRows = (values: Record<string, unknown>) =>
  Object.entries(values).map(([parameter, value]) => ({ parameter, value }));
function Dictionary({ values }: { values: Record<string, unknown> }) {
  return <Table rows={dictionaryRows(values)} columns={dictionaryColumns} />;
}
function Quality({ audit }: ViewProps) {
  const view = dashboardData(audit);
  return (
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
          {view.source} ·{" "}
          {audit.scope.daily_kpi_is_fact
            ? "Суточный факт W / Q_сут"
            : "УРЭ по режиму; суточный факт отсутствует"}
        </span>
      </div>
      {audit.quality.issues.length > 0 && (
        <ul className="warnings">
          {audit.quality.issues.map((issue, i) => (
            <li key={`${issue.code}-${i}`}>{issue.message}</li>
          ))}
        </ul>
      )}
    </>
  );
}
function Kpis({
  rows,
  label,
}: {
  rows: [string, unknown, string][];
  label: string;
}) {
  return (
    <section className="kpis" aria-label={label}>
      {rows.map(([name, value, unit]) => (
        <div className="kpi" key={name}>
          <span>{name}</span>
          <strong>
            {fmt(value, 3)} <small>{unit}</small>
          </strong>
        </div>
      ))}
    </section>
  );
}
function AnnualSummary({ audit }: ViewProps) {
  const view = dashboardData(audit);
  if (!view.usable)
    return (
      <p className="notice error">
        Годовая экономия скрыта: режим непригоден для экономических выводов.
      </p>
    );
  return (
    <Panel
      title="Годовая оценка"
      caption={`${view.runtime} T_год = ${fmt(audit.scope.annual_runtime_hours, 1)} ч · тариф ${fmt(audit.tariff)} ₽/кВт·ч. Годовая оценка — сценарий, не достигнутая экономия.`}
    >
      <Kpis
        label="Годовые потери"
        rows={[
          ["Потери по КПД", view.annual?.efficiency_energy_kwh, "кВт·ч/год"],
          [
            "Потери по КПД в деньгах",
            view.annual?.efficiency_money_krub,
            "тыс. ₽/год",
          ],
          [
            "Потери дросселирования",
            view.annual?.throttle_energy_kwh,
            "кВт·ч/год",
          ],
          [
            "Потери дросселирования в деньгах",
            view.annual?.throttle_money_krub,
            "тыс. ₽/год",
          ],
        ]}
      />
    </Panel>
  );
}
function Passport({ audit }: ViewProps) {
  const p = audit.passport?.pump,
    m = audit.passport?.motor,
    rm = audit.regime,
    view = dashboardData(audit);
  return (
    <Panel title="Паспорт и исходный режим">
      <div className="chart-grid">
        <div>
          <h3>Насос</h3>
          <Dictionary
            values={{
              Модель: p?.model,
              Тип: p?.kind,
              "Q_ном, м³/ч": p?.q_nom,
              "H_ном, м": p?.h_nom,
              "η_нас.ном, о.е.": p?.eta_nom,
              "P_ном, кВт": p?.power_nom,
              "n, об/мин": p?.n_rpm,
              "Кривая Q-H": p?.curve_qh?.length
                ? "Паспортные координаты"
                : "Отсутствует",
              "Кривая Q-η": p?.curve_qeta?.length
                ? "Паспортные координаты"
                : "Отсутствует",
            }}
          />
        </div>
        <div>
          <h3>Электродвигатель и передача</h3>
          <Dictionary
            values={{
              Модель: m?.model,
              Тип: m?.synchronous ? "синхронный" : "асинхронный",
              "P_ном, кВт": m?.p_nom,
              "η_ЭД.ном, о.е.": m?.eta_nom,
              "cos φ": m?.cos_phi,
              "U, кВ": m?.voltage_kv,
              ПЧ: audit.passport?.vfd ? "Есть" : "Нет",
              "КПД трансмиссии": audit.passport?.transmission?.efficiency,
            }}
          />
        </div>
      </div>
      <div className="chart-grid">
        <div>
          <h3>
            {view.source === "Телеметрия"
              ? "Показатель давления"
              : "Выездной замер"}
          </h3>
          <Dictionary
            values={{
              Источник: view.source,
              ...(view.timestamp
                ? { "Время замера": view.timestamp.replace("T", " ") }
                : {}),
              "p_вх, МПа": rm.p_in,
              "p_вых, МПа": rm.p_out,
              "p_БГ, МПа": rm.p_bg,
              "Δp, МПа": rm.p_out - rm.p_in,
            }}
          />
        </div>
        <div>
          <h3>Суточные данные и свойства жидкости</h3>
          <Dictionary
            values={{
              "ρ, кг/м³": rm.rho,
              "ν, сСт": rm.nu,
              "Q_сут, м³": rm.q_day,
              "Моточасы, ч": rm.t,
              "W, кВт·ч": rm.w,
              "Q мгновенный, м³/ч": rm.q_fact,
              "P_эл средняя, кВт": rm.p_electric,
              "T_год, ч": rm.t_year,
            }}
          />
        </div>
      </div>
    </Panel>
  );
}
function TopMeasures({ context }: { context: PageProps }) {
  const result = useResource<{ annual: Record<string, unknown>[] }>(
    `/objects/${segment(context.objectId)}/aggregates/${segment(context.aggregateId)}/measures`,
    contextBody(context, { basis: "annual" }),
  );
  return (
    <Panel
      title="Топ мероприятий"
      caption="Эвристическая оценка. Сценарные мероприятия требуют диагностики и оценки CAPEX."
    >
      <Status {...result} />
      {result.data && (
        <Table
          rows={result.data.annual.slice(0, 3).map((r) => ({
            ...r,
            payback:
              r.cls === "сценарная оценка"
                ? "требует оценки"
                : (r.payback_years ?? "без CAPEX"),
          }))}
          columns={[
            { key: "name", label: "Мероприятие" },
            { key: "energy_saving_kwh", label: "кВт·ч/год" },
            { key: "money_saving_krub", label: "тыс. ₽/год" },
            { key: "payback", label: "Окупаемость, лет" },
          ]}
        />
      )}
      <p className="muted">
        Полный реестр и ТЭО на горизонте — раздел «Мероприятия». Отсутствие
        применимого мероприятия не означает, что потери в норме.
      </p>
    </Panel>
  );
}
export function OverviewView({
  audit,
  context,
}: ViewProps & { context?: PageProps }) {
  const m = audit.audit.metrics,
    v = dashboardData(audit);
  return (
    <>
      <Quality audit={audit} />
      <Kpis
        label="Удельный расход энергии"
        rows={[
          ["УРЭ факт", m.sec_fact_kwh_m3, "кВт·ч/м³"],
          ["УРЭ расчётный", m.sec_calc_kwh_m3, "кВт·ч/м³"],
          [
            "УРЭ оптимальный",
            v.usable ? m.sec_optimal_kwh_m3 : null,
            "кВт·ч/м³",
          ],
          ["Цель ППД-2035", audit.target_sec, "кВт·ч/м³"],
        ]}
      />
      <Kpis
        label="Показатели режима"
        rows={[
          ["КПД агрегата", m.eta_unit, "о.е."],
          ["КПД номинальный", m.eta_nom, "о.е."],
          ["Коэффициент загрузки ЭД", m.load_factor, "о.е."],
          ["КПД ЭД расчётный", m.eta_motor_real, "о.е."],
          ["КПД насоса расчётный", m.eta_pump, "о.е."],
          ["Фактический напор", m.h_fact_m, "м"],
          ["Подача", m.flow_m3h, "м³/ч"],
          ["Гидравлическая мощность", m.p_hydraulic_kw, "кВт"],
          ["Электрическая мощность", m.p_electric_kw, "кВт"],
        ]}
      />
      {v.usable ? (
        <>
          <Panel title="Потери и мероприятия">
            <LossCharts
              power={m.p_electric_kw ?? 0}
              losses={v.losses}
              status={audit.quality.status}
              compact
            />
          </Panel>
          {context && <TopMeasures context={context} />}
          <Panel title="КПД и удельный расход энергии">
            <EfficiencyCharts metrics={m} target={audit.target_sec} />
          </Panel>
          <AnnualSummary audit={audit} />
        </>
      ) : (
        <p className="notice error">
          Потери, мероприятия и годовая экономия скрыты: режим непригоден для
          выводов.
        </p>
      )}
      <Passport audit={audit} />
    </>
  );
}
export function SnapshotView({ audit }: ViewProps) {
  const m = audit.audit.metrics,
    v = dashboardData(audit);
  return (
    <>
      <Quality audit={audit} />
      <Panel
        title="Режимный расчёт"
        caption={
          v.timestamp
            ? `Момент: ${v.timestamp.replace("T", " ")}`
            : "Выездной замер из YAML; время измерения не задано."
        }
      >
        <Kpis
          label="Режимный расчёт"
          rows={[
            ["Давление на приёме", audit.regime.p_in, "МПа"],
            ["Давление на выкиде", audit.regime.p_out, "МПа"],
            ["Давление БГ", audit.regime.p_bg, "МПа"],
            ["Напор факт", m.h_fact_m, "м"],
            ["Должный напор", m.h_due_m, "м"],
            ["Подача", m.flow_m3h, "м³/ч"],
            ["КПД на выбранный момент", m.eta_unit, "о.е."],
            ["УРЭ расчётный", m.sec_calc_kwh_m3, "кВт·ч/м³"],
          ]}
        />
        {audit.snapshot && (
          <p className="muted">
            С момента изменения мощности: {fmt(audit.snapshot.power_age_seconds, 0)} с;
            давления БГ: {fmt(audit.snapshot.p_bg_age_seconds, 0)} с.
          </p>
        )}
      </Panel>
      <Panel title="Суточный факт">
        <p>
          {audit.scope.daily_kpi_is_fact
            ? `УРЭ факт W / Q_сут = ${fmt(m.sec_fact_kwh_m3, 3)} кВт·ч/м³.`
            : "Нет W и Q_сут: суточный фактический УРЭ не вычисляется."}
        </p>
        <Dictionary
          values={{
            "W, кВт·ч": audit.regime.w,
            "Q_сут, м³": audit.regime.q_day,
            "T, ч": audit.regime.t,
            "Мощность для расчёта, кВт": m.p_electric_kw,
          }}
        />
      </Panel>
      <SourcesView audit={audit} />
      <AnnualSummary audit={audit} />
    </>
  );
}
export function SourcesView({ audit }: ViewProps) {
  const v = dashboardData(audit);
  return (
    <>
      <Panel title="Источники расчётных входов" caption={v.source}>
        {Object.keys(audit.sources).length ? (
          <Dictionary values={audit.sources} />
        ) : (
          <p className="notice">
            Источники не сохранены у ранее загруженной телеметрии.
          </p>
        )}
      </Panel>
      <Panel title="Основание расчётных показателей">
        <Dictionary
          values={Object.fromEntries(
            Object.entries(audit.quality.basis).map(([key, value]) => [
              basisLabel[key] ?? key,
              value,
            ]),
          )}
        />
        <p className="muted">
          {v.runtime} T_год = {fmt(audit.scope.annual_runtime_hours)} ч.{" "}
          {audit.scope.daily_kpi_is_fact
            ? "Суточный УРЭ основан на W / Q_сут."
            : "Расход энергии относится к расчётному режиму."}
        </p>
      </Panel>
    </>
  );
}
export function LossesView({ audit }: ViewProps) {
  const v = dashboardData(audit);
  return (
    <Panel
      title="Цифровая карта потерь мощности"
      caption={`${v.runtime} T_год = ${fmt(audit.scope.annual_runtime_hours)} ч; тариф ${fmt(audit.tariff)} ₽/кВт·ч.`}
    >
      {v.usable ? (
        <>
          <LossCharts
            power={audit.audit.metrics.p_electric_kw ?? 0}
            losses={v.losses}
            status={audit.quality.status}
          />
          <Table
            rows={v.losses.map((loss: Audit["losses"][number]) => ({
              ...loss,
              percent: loss.share * 100,
            }))}
            columns={[
              { key: "name", label: "Составляющая" },
              { key: "power_kw", label: "Мощность, кВт" },
              { key: "percent", label: "Доля, %" },
              { key: "annual_kwh", label: "Энергия, кВт·ч/год" },
              { key: "annual_rub", label: "Стоимость, ₽/год" },
            ]}
          />
          <p className="muted">
            Годовые суммы —{" "}
            {audit.scope.annual_runtime_is_assumed
              ? "сценарий непрерывной работы"
              : audit.source === "field_trip"
                ? "выездная оценка"
                : "оценка по телеметрии"}
            , не фактически достигнутая экономия.
          </p>
        </>
      ) : (
        <p className="notice error">
          Карта потерь не построена: режим непригоден для экономических выводов.
        </p>
      )}
    </Panel>
  );
}
