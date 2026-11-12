import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { Panel } from "../../shared/ui/Panel";
import { fmt } from "../../shared/ui/format";
import { DailyFacts } from "./DailyFacts";
import { Diagnostics } from "./Diagnostics";
import { Kpis } from "./Kpis";
import { Quality } from "./Quality";

export function SnapshotView({ audit }: { audit: Audit }) {
  const m = audit.audit.metrics, view = dashboardData(audit);
  const rows: [string, unknown, string][] = [
    ["Давление на приёме", audit.regime.p_in, "МПа"],
    ["Давление на выкиде", audit.regime.p_out, "МПа"],
    ["Давление БГ", audit.regime.p_bg, "МПа"],
    ["Напор факт", m.h_fact_m, "м"],
    ["Должный напор", m.h_due_m, "м"],
    ["Подача", m.flow_m3h, "м³/ч"],
    ["Электрическая мощность", m.p_electric_kw, "кВт"],
    ["Средняя за часы работы · W/T", m.power_operating_avg_kw, "кВт"],
    ["Средняя за календарные сутки · W/24", m.power_daily_avg_kw, "кВт"],
    ["Мощность суточного отчёта · база неизвестна", m.power_daily_reported_kw, "кВт"],
    ["КПД на выбранный момент", m.eta_unit, "о.е."],
    ["УРЭ расчётный", m.sec_calc_kwh_m3, "кВт·ч/м³"],
  ];
  if (!audit.scope.daily_kpi_is_fact) rows.push(["УРЭ по режиму", view.regimeSec, "кВт·ч/м³"]);
  return (
    <>
      <Quality audit={audit} />
      <DailyFacts audit={audit} />
      <Panel title="Режимный расчёт" caption={view.regimeBasis}>
        <p className="muted">Подача: {audit.quality.basis.flow ?? "источник не указан"}. Мощность: {audit.quality.basis.power ?? "источник не указан"}. Суточный факт и этот расчёт имеют разную временную базу.</p>
        <Kpis audit={audit} label="Режимный расчёт" heading={false} rows={rows} />
        {audit.snapshot && <p className="muted">
          С момента изменения мощности: {fmt(audit.snapshot.power_age_seconds, 0)} с; давления БГ: {fmt(audit.snapshot.p_bg_age_seconds, 0)} с.
        </p>}
      </Panel>
      <Diagnostics report={audit.diagnostics} />
    </>
  );
}
