import { metricLinks } from "../inspection/inspection.mjs";
import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { metricAssessment } from "../../shared/metrics/metricAssessment.mjs";
import { MetricCard, type MetricSegment } from "../../shared/ui/MetricCard";
import { Panel } from "../../shared/ui/Panel";
import { fmt } from "../../shared/ui/format";

export function AnnualSummary({ audit }: { audit: Audit }) {
  const view = dashboardData(audit);
  if (!view.usable)
    return <p className="notice error">Годовая экономия скрыта: режим непригоден для экономических выводов.</p>;
  const segment = (label: string, value: unknown, unit: string, help: string): MetricSegment => {
    const assessment = metricAssessment(value, 0, "higher", true);
    return { label, value, unit, help, tone: "neutral", reason: assessment.reason };
  };
  return (
    <Panel
      title="Годовая оценка"
      help={`${view.runtime} Годовая наработка: ${fmt(audit.scope.annual_runtime_hours, 1)} ч. Тариф: ${fmt(audit.tariff)} ₽/кВт·ч. Годовая оценка — сценарий, не достигнутая экономия.`}
    >
      <section className="metric-group annual-group" aria-label="Показатели годовой оценки">
        <div className="kpis">
          <MetricCard
            links={metricLinks("efficiency_loss")}
            label="Потери по КПД"
            value={null}
            unit=""
            help="Годовая потеря энергии по КПД и её денежная оценка. Сценарий по T_год, не достигнутая экономия."
            segments={[
              segment("Энергия", view.annual?.efficiency_energy_kwh, "кВт·ч/год", "Годовая энергия потерь по КПД."),
              segment("Деньги", view.annual?.efficiency_money_krub, "тыс. ₽/год", "Эта сумма — стоимость потерь по тарифу, а не затраты на проведение мероприятия."),
            ]}
          />
          <MetricCard
            links={metricLinks("throttle_loss")}
            label="Потери дросселирования"
            value={null}
            unit=""
            help="Годовая потеря энергии из-за дросселирования и её денежная оценка. Сценарий требует подтверждения оптимального режима."
            segments={[
              segment("Энергия", view.annual?.throttle_energy_kwh, "кВт·ч/год", "Годовая энергия потерь дросселирования."),
              segment("Деньги", view.annual?.throttle_money_krub, "тыс. ₽/год", "Эта сумма — стоимость потерь по тарифу, а не затраты на проведение мероприятия."),
            ]}
          />
        </div>
      </section>
    </Panel>
  );
}
