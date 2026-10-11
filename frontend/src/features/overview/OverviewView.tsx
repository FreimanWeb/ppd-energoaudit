import { metricLinks } from "../inspection/inspection.mjs";
import { type ReactNode } from "react";
import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { metricAssessment } from "../../shared/metrics/metricAssessment.mjs";
import { MetricCard } from "../../shared/ui/MetricCard";
import type { PageProps } from "../../shared/ui/context";
import { AnnualSummary } from "./AnnualSummary";
import { EfficiencyKpiPanel } from "./EfficiencyKpiPanel";
import { OverviewMetricPanel } from "./OverviewMetricPanel";
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
      <div className="overview-primary">
        <OverviewMetricPanel title="Удельный расход энергии" actionLabel="Ориентиры УРЭ" layout="ure" details={<MetricCard label="" value={null} unit="" help="" segments={[
          { label: "Цель ППД-2035", value: audit.target_sec, unit: "кВт·ч/м³", help: metricHelp["Цель ППД-2035"], ...metricAssessment(audit.target_sec, null, "higher", v.usable) },
        ]} />}>
          <MetricCard label="" value={null} unit="" help="" segments={[
            { label: "Факт", links: metricLinks("sec_fact"), value: m.sec_fact_kwh_m3, unit: "кВт·ч/м³", help: metricHelp["УРЭ факт"], ...metricAssessment(m.sec_fact_kwh_m3, m.sec_calc_kwh_m3, "higher", v.usable) },
            { label: "Расчётный", links: metricLinks("sec_calc"), value: m.sec_calc_kwh_m3, unit: "кВт·ч/м³", help: metricHelp["УРЭ расчётный"], ...metricAssessment(m.sec_calc_kwh_m3, null, "higher", v.usable) },
            { label: "Оптимальный", links: metricLinks("sec_optimal"), value: v.usable ? m.sec_optimal_kwh_m3 : null, unit: "кВт·ч/м³", help: metricHelp["УРЭ оптимальный"], ...metricAssessment(v.usable ? m.sec_optimal_kwh_m3 : null, null, "higher", v.usable) },
          ]} />
        </OverviewMetricPanel>
      <EfficiencyKpiPanel audit={audit} />
      </div>
      {scheme}
      {v.usable ? (
        <>
          <AnnualSummary audit={audit} />
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
