import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { Panel } from "../../shared/ui/Panel";
import { fmt } from "../../shared/ui/format";
import { Dictionary } from "./Dictionary";

const basisLabel: Record<string, string> = {
  pressure: "Давление",
  flow: "Подача",
  power: "Мощность",
};

export function SourcesView({ audit }: { audit: Audit }) {
  const view = dashboardData(audit);
  return (
    <>
      <Panel title="Источники расчётных входов" caption={view.source}>
        {Object.keys(audit.sources).length ? <Dictionary values={audit.sources} /> : <p className="notice">Источники не сохранены у ранее загруженной телеметрии.</p>}
      </Panel>
      <Panel title="Основание расчётных показателей">
        <Dictionary values={Object.fromEntries(Object.entries(audit.quality.basis).map(([key, value]) => [basisLabel[key] ?? key, value]))} />
        <p className="muted">
          {view.runtime} T_год = {fmt(audit.scope.annual_runtime_hours)} ч.{" "}
          {audit.scope.daily_kpi_is_fact ? "Суточный УРЭ основан на W / Q_сут." : "Расход энергии относится к расчётному режиму."}
        </p>
      </Panel>
    </>
  );
}
