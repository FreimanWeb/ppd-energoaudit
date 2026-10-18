import { efficiencyPercent } from "../../shared/format/number.mjs";
import { metricLinks } from "../inspection/inspection.mjs";
import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { metricAssessment } from "../../shared/metrics/metricAssessment.mjs";
import { MetricCard } from "../../shared/ui/MetricCard";
import { fmt } from "../../shared/ui/format";
import { Kpis, metricHelp } from "./Kpis";
import { Panel } from "../../shared/ui/Panel";

export function EfficiencyKpiPanel({ audit }: { audit: Audit }) {
  const { eta_unit: actual, eta_nom: nominal } = audit.audit.metrics;
  const usable = dashboardData(audit).usable;
  const actualAssessment = metricAssessment(actual, nominal, "lower", usable, true);
  const nominalAssessment = metricAssessment(nominal, null, "higher", usable, true);
  const difference = usable && actual != null && nominal != null && Number.isFinite(actual) && Number.isFinite(nominal)
    && actual >= 0 && actual <= 1 && nominal > 0 && nominal <= 1
      ? Number(((actual - nominal) * 100).toFixed(1)) : null;
  const actualCaption = actualAssessment.caption !== "Физическая ошибка" && (actualAssessment.tone === "good" || actualAssessment.tone === "bad")
    ? actual === nominal ? "На уровне номинального" : Number(actual) > Number(nominal) ? "Выше номинального" : "Ниже номинального"
    : actualAssessment.caption;

  return (
    <Panel title="КПД">
      <div className="machine-efficiency">
        <MetricCard label="" value={null} unit="" help="" segments={[
            { label: "КПД агрегата", links: metricLinks("eta_unit"), value: efficiencyPercent(actual), unit: "%", help: metricHelp["КПД агрегата"],
              ...actualAssessment,
              valueSuffix: difference != null && difference !== 0 ? <sup className="efficiency-difference" aria-label="Разница КПД"><b className="efficiency-difference-arrow">{difference < 0 ? "↓" : "↑"}</b><span className="efficiency-difference-value">{fmt(Math.abs(difference), 1)}</span></sup> : null,
              reason: [actualCaption, actualAssessment.reason, difference != null && difference !== 0 ? `Отклонение от номинального: ${difference > 0 ? "+" : ""}${fmt(difference, 1)} п.п.` : null].filter(Boolean).join(". ") },
            { label: "КПД номинальный", links: metricLinks("eta_nom"), value: efficiencyPercent(nominal), unit: "%", help: metricHelp["КПД номинальный"], ...nominalAssessment },
        ]} />
        <Kpis audit={audit} label="Показатели агрегата" heading={false} rows={[
          ["Коэффициент загрузки ЭД", audit.audit.metrics.load_factor, "о.е."],
          ["КПД ЭД расчётный", audit.audit.metrics.eta_motor_real, "о.е."],
          ["КПД насоса расчётный", audit.audit.metrics.eta_pump, "о.е."],
        ]} />
      </div>
    </Panel>
  );
}
