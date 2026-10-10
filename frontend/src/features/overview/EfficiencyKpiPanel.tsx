import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { metricAssessment } from "../../shared/metrics/metricAssessment.mjs";
import { MetricCard } from "../../shared/ui/MetricCard";
import { EfficiencyCharts } from "../metrics/EfficiencyCharts";
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
    <Panel title="КПД агрегата и КПД номинальный">
      <section className="metric-group efficiency-group" aria-label="КПД агрегата и КПД номинальный">
        <div className="kpis">
          <MetricCard label="КПД агрегата" value={actual} unit="о.е."
            help="Фактический КПД установки: гидравлическая мощность / электрическая мощность. Сравнение с номинальным КПД."
            {...actualAssessment} caption={actualCaption} />
          <MetricCard label="КПД номинальный" value={nominal} unit="о.е."
            help="Паспортный КПД установки: произведение КПД двигателя, насоса и передачи."
            {...nominalAssessment} />
          {usable && (
            <div className="metric-efficiency-disclosure">
              <details className="metric-disclosure">
                <summary>Светофор КПД</summary>
                <EfficiencyCharts metrics={audit.audit.metrics} usable={usable} />
              </details>
            </div>
          )}
        </div>
      </section>
    </Panel>
  );
}
