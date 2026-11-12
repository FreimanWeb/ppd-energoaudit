import { LinkButton } from "../../shared/ui/Button";
import { metricLinks, inspectionHref } from "../inspection/inspection.mjs";
import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { metricAssessment } from "../../shared/metrics/metricAssessment.mjs";
import { MetricCard } from "../../shared/ui/MetricCard";
import { EfficiencyKpiPanel } from "./EfficiencyKpiPanel";
import { Panel } from "../../shared/ui/Panel";
import { metricHelp } from "./Kpis";
import { DailyFacts } from "./DailyFacts";
import "./overview.css";

export function OverviewView({ audit }: { audit: Audit }) {
  const m = audit.audit.metrics, v = dashboardData(audit);
  const errors = audit.quality.issues.filter(issue => issue.severity === "error");
  const triggered = audit.diagnostics.rules.filter(rule => rule.status === "triggered");
  const hasDaily = audit.scope.daily_kpi_is_fact || audit.regime.w != null || audit.regime.q_day != null || audit.regime.t != null;
  return (
    <div className="overview-page">
      {(errors.length > 0 || audit.quality.status === "unfit") && <p className="notice error" role="alert">
        {errors.length ? [...new Set(errors.map(issue => issue.message))].join(" ") : "Данные непригодны для достоверных выводов."}
      </p>}
      {hasDaily && <DailyFacts audit={audit} />}
      <section aria-label="Расчёт выбранного режима">
      <h2>Расчёт выбранного режима</h2>
      <p className="muted">{v.regimeBasis} Суточные итоги показаны отдельно; ниже — расчёт по доступным исходным данным режима.</p>
      <div className="overview-primary machine-kpi-panels">
        <Panel title="Удельный расход энергии">
          <div className="machine-ure overview-metric-values-ure">
            <MetricCard label="" value={null} unit="" help="" segments={[
              ...(!audit.scope.daily_kpi_is_fact ? [{
                label: "По режиму", links: metricLinks("sec_regime"), value: v.regimeSec, unit: "кВт·ч/м³", help: metricHelp["УРЭ по режиму"], ...metricAssessment(v.regimeSec, m.sec_calc_kwh_m3, "higher", v.usable),
              }] : []),
              { label: "При паспортном КПД", links: metricLinks("sec_calc"), value: m.sec_calc_kwh_m3, unit: "кВт·ч/м³", help: metricHelp["УРЭ расчётный"], ...metricAssessment(m.sec_calc_kwh_m3, null, "higher", v.usable) },
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
      </section>
      {triggered.length > 0 && <section aria-label="Существенные отклонения">
        <h3>Отклонения для проверки</h3>
        <ul>{triggered.map(rule => <li key={rule.id}><strong>{rule.title}.</strong> {rule.action || rule.reason}</li>)}</ul>
      </section>}
      <nav className="content-actions" aria-label="Подробности агрегата">
        <LinkButton href={inspectionHref("sources", undefined)}>Паспорт и источники</LinkButton>
        <LinkButton href={inspectionHref("snapshot", undefined)}>Полная диагностика</LinkButton>
        <LinkButton href={inspectionHref("formulas", "annual_losses")}>Годовая оценка</LinkButton>
      </nav>
    </div>
  );
}
