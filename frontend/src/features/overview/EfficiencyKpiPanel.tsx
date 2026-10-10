import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { metricAssessment } from "../../shared/metrics/metricAssessment.mjs";
import { MetricCard } from "../../shared/ui/MetricCard";
import { EfficiencyCharts } from "../metrics/EfficiencyCharts";
import { Kpis, metricHelp } from "./Kpis";
import { Panel } from "../../shared/ui/Panel";

export function EfficiencyKpiPanel({ audit }: { audit: Audit }) {
  const { eta_unit: actual, eta_nom: nominal } = audit.audit.metrics;
  const usable = dashboardData(audit).usable;
  const actualAssessment = metricAssessment(actual, nominal, "lower", usable, true);
  const nominalAssessment = metricAssessment(nominal, null, "higher", usable, true);
  const actualCaption = actualAssessment.caption !== "Физическая ошибка" && (actualAssessment.tone === "good" || actualAssessment.tone === "bad")
    ? actual === nominal ? "На уровне номинального" : Number(actual) > Number(nominal) ? "Выше номинального" : "Ниже номинального"
    : actualAssessment.caption;

  return (
    <Panel title="КПД">
      <section className="metric-group efficiency-group" aria-label="КПД">
          <MetricCard label="" value={null} unit="" help="" segments={[
            { label: "КПД агрегата", value: actual, unit: "о.е.", help: metricHelp["КПД агрегата"],
              ...actualAssessment, reason: [actualCaption, actualAssessment.reason].filter(Boolean).join(". ") },
            { label: "КПД номинальный", value: nominal, unit: "о.е.", help: metricHelp["КПД номинальный"], ...nominalAssessment },
          ]} />
          {usable && (
            <div className="metric-efficiency-disclosure">
              <details className="metric-disclosure">
                <summary>Светофор КПД</summary>
                <EfficiencyCharts metrics={audit.audit.metrics} usable={usable} />
              </details>
            </div>
          )}
          <details className="metric-disclosure">
            <summary>Диагностика агрегата</summary>
            <Kpis audit={audit} label="Диагностика агрегата" heading={false} rows={[
              ["Коэффициент загрузки ЭД", audit.audit.metrics.load_factor, "о.е."],
              ["КПД ЭД расчётный", audit.audit.metrics.eta_motor_real, "о.е."],
              ["КПД насоса расчётный", audit.audit.metrics.eta_pump, "о.е."],
            ]} />
          </details>
      </section>
    </Panel>
  );
}
