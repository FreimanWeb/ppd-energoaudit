import type { Audit } from "../../shared/types";
import { MetricCard } from "../../shared/ui/MetricCard";
import { Panel } from "../../shared/ui/Panel";
import { metricLinks } from "../inspection/inspection.mjs";
import { dashboardData } from "./dashboardData.mjs";
import { metricHelp } from "./Kpis";

export function DailyFacts({ audit }: { audit: Audit }) {
  const view = dashboardData(audit);
  const caption = audit.source === "field_trip"
    ? "Суточные исходные данные из YAML. Дата суточного итога не задана; это не текущая телеметрия."
    : view.timestamp
      ? `Телеметрия за сутки ${view.timestamp.slice(0, 10)}. Итоги суток не относятся только к выбранному моменту.`
      : "Суточные исходные данные телеметрии; дата итога не задана.";
  return <Panel title="Суточный факт" caption={caption}>
    {!audit.scope.daily_kpi_is_fact && <p className="notice">Суточный УРЭ не определён: нужны энергия и объём за одни и те же сутки. Расчёт выбранного режима его не подменяет.</p>}
    <div className="station-kpis">
      <MetricCard label="УРЭ за сутки" value={view.dailySec} unit="кВт·ч/м³" help={metricHelp["УРЭ факт"]} links={metricLinks("sec_fact")} />
      <MetricCard label="Энергия за сутки" value={audit.regime.w} unit="кВт·ч" help="Суточная электрическая энергия W. Мгновенная мощность не подставляется вместо энергии." />
      <MetricCard label="Закачка за сутки" value={audit.regime.q_day} unit="м³" help="Суточный объём закачки Q_сут. Мгновенная подача не подставляется вместо объёма." />
      <MetricCard label="Наработка за сутки" value={audit.regime.t} unit="ч" help="Продолжительность работы за те же сутки, а не годовая наработка сценария." />
    </div>
    {audit.scope.daily_kpi_is_fact && <p className="muted">УРЭ = W / Q_сут. Сравнение суточного итога с расчётом по отдельному замеру давления не подтверждает величину потерь.</p>}
  </Panel>;
}
