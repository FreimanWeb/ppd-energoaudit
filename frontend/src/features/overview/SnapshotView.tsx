import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { Panel } from "../../shared/ui/Panel";
import { fmt } from "../../shared/ui/format";
import { Dictionary } from "./Dictionary";
import { Kpis } from "./Kpis";
import { Quality } from "./Quality";

export function SnapshotView({ audit }: { audit: Audit }) {
  const m = audit.audit.metrics, view = dashboardData(audit);
  return (
    <>
      <Quality audit={audit} />
      <Panel title="Режимный расчёт" caption={view.timestamp ? `Момент: ${view.timestamp.replace("T", " ")}` : "Выездной замер из YAML; время измерения не задано."}>
        <Kpis audit={audit} label="Режимный расчёт" heading={false} rows={[
          ["Давление на приёме", audit.regime.p_in, "МПа"],
          ["Давление на выкиде", audit.regime.p_out, "МПа"],
          ["Давление БГ", audit.regime.p_bg, "МПа"],
          ["Напор факт", m.h_fact_m, "м"],
          ["Должный напор", m.h_due_m, "м"],
          ["Подача", m.flow_m3h, "м³/ч"],
          ["КПД на выбранный момент", m.eta_unit, "о.е."],
          ["УРЭ расчётный", m.sec_calc_kwh_m3, "кВт·ч/м³"],
        ]} />
        {audit.snapshot && <p className="muted">
          С момента изменения мощности: {fmt(audit.snapshot.power_age_seconds, 0)} с; давления БГ: {fmt(audit.snapshot.p_bg_age_seconds, 0)} с.
        </p>}
      </Panel>
      <Panel title="Суточный факт">
        <p>{audit.scope.daily_kpi_is_fact
          ? `УРЭ факт W / Q_сут = ${fmt(m.sec_fact_kwh_m3, 3)} кВт·ч/м³.`
          : "Нет W и Q_сут: суточный фактический УРЭ не вычисляется."}</p>
        <Dictionary values={{ "W, кВт·ч": audit.regime.w, "Q_сут, м³": audit.regime.q_day, "T, ч": audit.regime.t, "Мощность для расчёта, кВт": m.p_electric_kw }} />
      </Panel>
    </>
  );
}
