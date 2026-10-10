import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { metricAssessment } from "../../shared/metrics/metricAssessment.mjs";
import { MetricCard } from "../../shared/ui/MetricCard";
import { Panel } from "../../shared/ui/Panel";
import type { PageProps } from "../../shared/ui/context";
import { AnnualSummary } from "./AnnualSummary";
import { EfficiencyKpiPanel } from "./EfficiencyKpiPanel";
import { Kpis, metricHelp } from "./Kpis";
import { Passport } from "./Passport";
import { Quality } from "./Quality";
import { TopMeasures } from "./TopMeasures";
import "./overview.css";

export function OverviewView({ audit, context }: { audit: Audit; context?: PageProps }) {
  const m = audit.audit.metrics, v = dashboardData(audit);
  return (
    <div className="overview-page">
      <Quality audit={audit} />
      <div className="overview-primary">
      <section className="page-panel ure-panel" aria-label="Удельный расход энергии">
        <header className="metric-toolbar">
          <h2>Удельный расход энергии</h2>
        </header>
          <MetricCard label="" value={null} unit="" help="" segments={[
            { label: "Факт", value: m.sec_fact_kwh_m3, unit: "кВт·ч/м³", help: metricHelp["УРЭ факт"], ...metricAssessment(m.sec_fact_kwh_m3, m.sec_calc_kwh_m3, "higher", v.usable) },
            { label: "Расчётный", value: m.sec_calc_kwh_m3, unit: "кВт·ч/м³", help: metricHelp["УРЭ расчётный"], ...metricAssessment(m.sec_calc_kwh_m3, null, "higher", v.usable) },
            { label: "Оптимальный", value: v.usable ? m.sec_optimal_kwh_m3 : null, unit: "кВт·ч/м³", help: metricHelp["УРЭ оптимальный"], ...metricAssessment(v.usable ? m.sec_optimal_kwh_m3 : null, null, "higher", v.usable) },
            { label: "Цель ППД-2035", value: audit.target_sec, unit: "кВт·ч/м³", help: metricHelp["Цель ППД-2035"], ...metricAssessment(audit.target_sec, null, "higher", v.usable) },
          ]} />
      </section>
      <EfficiencyKpiPanel audit={audit} />
      </div>
      <div className="overview-secondary">
      <Panel title="Рабочий режим">
      <Kpis audit={audit} label="Рабочий режим" heading={false} rows={[
        ["Фактический напор", m.h_fact_m, "м"],
        ["Подача", m.flow_m3h, "м³/ч"],
        ["Гидравлическая мощность", m.p_hydraulic_kw, "кВт"],
        ["Электрическая мощность", m.p_electric_kw, "кВт"],
      ]} />
      </Panel>
      <Panel title="Состояние оборудования">
      <Kpis audit={audit} label="Состояние оборудования" heading={false} rows={[
        ["Коэффициент загрузки ЭД", m.load_factor, "о.е."],
        ["КПД ЭД расчётный", m.eta_motor_real, "о.е."],
        ["КПД насоса расчётный", m.eta_pump, "о.е."],
      ]} />
      </Panel>
      </div>
      {v.usable ? (
        <>
          <AnnualSummary audit={audit} />
          <a className="overview-section-link" href="#losses">Карта потерь мощности →</a>
          {context && <TopMeasures context={context} />}
        </>
      ) : (
        <div className="notice error" role="status">
          <strong>Недостаточно достоверных данных для оценки потерь</strong>
          <p>Проверьте замечания выше и исходные измерения. Можно выбрать другую дату или момент измерения.</p>
          <a href="#sources">Проверить источники данных</a>
        </div>
      )}
      <Passport audit={audit} />
    </div>
  );
}
