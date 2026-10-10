import { useState } from "react";
import type { Audit } from "../../shared/types";
import { dashboardData } from "../overview/dashboardData.mjs";
import { LossCharts } from "./LossCharts";
import { Panel } from "../../shared/ui/Panel";
import { Table } from "../../shared/ui/Table";
import { fmt } from "../../shared/ui/format";

export function LossesView({ audit }: { audit: Audit }) {
  const [mode, setMode] = useState<"decomposition" | "flow" | "percentage">("decomposition");
  const view = dashboardData(audit);
  return (
    <Panel title="Цифровая карта потерь мощности" help={`${view.runtime} Годовая наработка: ${fmt(audit.scope.annual_runtime_hours)} ч; тариф ${fmt(audit.tariff)} ₽/кВт·ч.`}>
      {view.usable ? (
        <>
          {view.losses.length > 0 && <div className="metric-toolbar">
            <div className="metric-segments" role="group" aria-label="Представление карты потерь">
              <button type="button" aria-pressed={mode === "decomposition"} onClick={() => setMode("decomposition")}>Разложение</button>
              <button type="button" aria-pressed={mode === "flow"} onClick={() => setMode("flow")}>Поток мощности</button>
              <button type="button" aria-pressed={mode === "percentage"} onClick={() => setMode("percentage")}>Структура, %</button>
            </div>
          </div>}
          <LossCharts power={audit.audit.metrics.p_electric_kw ?? 0} losses={view.losses} status={audit.quality.status} mode={mode} />
          <details><summary>Таблица составляющих</summary>
          <Table
            rows={view.losses.map((loss: Audit["losses"][number]) => ({ ...loss, percent: loss.share * 100 }))}
            columns={[
              { key: "name", label: "Составляющая" },
              { key: "power_kw", label: "Мощность, кВт" },
              { key: "percent", label: "Доля, %" },
              { key: "annual_kwh", label: "Энергия, кВт·ч/год" },
              { key: "annual_rub", label: "Стоимость, ₽/год" },
            ]}
          />
          </details>
          <p className="muted">
            Годовые суммы — {audit.scope.annual_runtime_is_assumed
              ? "сценарий непрерывной работы"
              : audit.source === "field_trip" ? "выездная оценка" : "оценка по телеметрии"}, не фактически достигнутая экономия.
          </p>
        </>
      ) : <p className="notice error">Карта потерь не построена: режим непригоден для экономических выводов.</p>}
    </Panel>
  );
}
