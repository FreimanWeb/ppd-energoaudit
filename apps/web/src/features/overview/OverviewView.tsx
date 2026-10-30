import { LinkButton } from "../../shared/ui/Button";
import { metricLinks } from "../inspection/inspection.mjs";
import { type ReactNode } from "react";
import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { metricAssessment } from "../../shared/metrics/metricAssessment.mjs";
import { MetricCard } from "../../shared/ui/MetricCard";
import type { PageProps } from "../../shared/ui/context";
import { EfficiencyKpiPanel } from "./EfficiencyKpiPanel";
import { Diagnostics } from "./Diagnostics";
import { AnnualSummary } from "./AnnualSummary";
import { Panel } from "../../shared/ui/Panel";
import { metricHelp } from "./Kpis";
import { Passport } from "./Passport";
import { Quality } from "./Quality";
import { TopMeasures } from "./TopMeasures";
import "./overview.css";

export function OverviewView({ audit, context, scheme, clarifications }: { audit: Audit; context?: PageProps; scheme?: ReactNode; clarifications?: {field: string; provisional_value: number | string; reason: string}[] }) {
  const m = audit.audit.metrics, v = dashboardData(audit);
  return (
    <div className="overview-page">
      <Quality audit={audit} clarifications={clarifications} />
      <p className="muted">УРЭ выбранного агрегата {audit.audit.aggregate_id}: электрическая энергия на объём его закачки. Суммарный УРЭ станции доступен в истории при выборе «Вся станция».</p>
      <div className="overview-primary machine-kpi-panels">
        <Panel title="Удельный расход энергии">
          <div className="machine-ure overview-metric-values-ure">
            <MetricCard label="" value={null} unit="" help="" segments={[
              { label: "Факт", links: metricLinks("sec_fact"), value: m.sec_fact_kwh_m3, unit: "кВт·ч/м³", help: metricHelp["УРЭ факт"], ...metricAssessment(m.sec_fact_kwh_m3, m.sec_calc_kwh_m3, "higher", v.usable) },
              { label: "Расчётный", links: metricLinks("sec_calc"), value: m.sec_calc_kwh_m3, unit: "кВт·ч/м³", help: metricHelp["УРЭ расчётный"], ...metricAssessment(m.sec_calc_kwh_m3, null, "higher", v.usable) },
            ]}/>
            <div className="machine-kpi-secondary">
              <MetricCard label="" value={null} unit="" help="" segments={[
                { label: "Оптимальный", links: metricLinks("sec_optimal"), value: v.usable ? m.sec_optimal_kwh_m3 : null, unit: "кВт·ч/м³", help: metricHelp["УРЭ оптимальный"], ...metricAssessment(v.usable ? m.sec_optimal_kwh_m3 : null, null, "higher", v.usable) },
                { label: "Цель ППД-2035", value: audit.target_sec, unit: "кВт·ч/м³", help: metricHelp["Цель ППД-2035"], ...metricAssessment(audit.target_sec, null, "higher", v.usable) },
              ]}/>
            </div>
          </div>
        </Panel>
        <EfficiencyKpiPanel audit={audit} />
      </div>
      {scheme}
      <Diagnostics report={audit.diagnostics} />
      {v.usable ? (
        <>
          <AnnualSummary audit={audit} />
          {context && <TopMeasures context={context} />}
        </>
      ) : (
        <div className="notice error" role="status">
          <strong>Недостаточно достоверных данных для оценки потерь</strong>
          <p>Проверьте замечания выше и исходные измерения. Можно выбрать другую дату или момент измерения.</p>
          <LinkButton href="#sources">Проверить источники данных</LinkButton>
        </div>
      )}
      <Passport audit={audit} />
    </div>
  );
}
