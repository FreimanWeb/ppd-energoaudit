import type { ReactNode } from "react";
import { formatEfficiency } from "../../shared/format/number.mjs";
import type { Audit, Equipment, Topology } from "../../shared/types";
import { fmt } from "../../shared/ui/format";
import { Scheme } from "./Scheme";

export function SchemePanel({
  topology,
  audit,
  aggregate,
  pressures,
  selected,
  onSelect,
  onClear,
  status,
}: {
  topology?: Topology;
  audit: Audit;
  aggregate: string;
  pressures?: Record<string, { p_in_mpa: number; p_out_mpa: number }>;
  selected: string;
  onSelect: (node: Equipment) => void;
  onClear: () => void;
  status?: ReactNode;
}) {
  const node =
    topology?.nodes.find((item) => item.id === selected) ??
    topology?.nodes.find((item) => item.agg === aggregate);
  const selectedNode = selected
    ? topology?.nodes.find((item) => item.id === selected)
    : undefined;
  const metrics = audit.audit.metrics;

  return (
    <section className="scheme-panel" aria-label="Технологическая схема ППД">
      <div className="section-heading"><h2>Технологическая схема ППД</h2></div>
      {status}
      {topology && <>
        <div className="scheme-layout">
          <div className="scheme-canvas">
            <Scheme
              key={audit.audit.object_id}
              topology={topology}
              aggregate={aggregate}
              audit={audit}
              pressures={pressures}
              selected={node?.id ?? ""}
              onSelect={onSelect}
            />
            {selectedNode && <aside className="scheme-node-popover" aria-label="Выбранное оборудование">
              <button type="button" className="scheme-node-popover-close" aria-label="Закрыть сведения об узле" onClick={onClear}>×</button>
              <div className="eyebrow">ОБОРУДОВАНИЕ</div>
              <h3>{selectedNode.label || selectedNode.id}</h3>
              {selectedNode.sub && <p>{selectedNode.sub}</p>}
              {selectedNode.hint && <p className="muted">{selectedNode.hint}</p>}
              {!selectedNode.hint && <p className="muted">{({
                valve: "дросселирование: срезается ΔP·Q; кандидат на частотное регулирование",
                wells: "Приёмистость P–Q; ограничение по лимиту закачки",
                reservoir: "Отклик пласта (CRM): полезная и циркулирующая закачка",
              } as Record<string, string>)[selectedNode.type]}</p>}
              {selectedNode.type === "source" && <dl>
                <dt>Давление на приёме</dt><dd>{fmt(audit.regime.p_in)} МПа</dd>
                <dt>Подача за сутки</dt><dd>{fmt(audit.regime.q_day, 0)} м³/сут</dd>
              </dl>}
              {selectedNode.type === "manifold" && <dl>
                <dt>Давление БГ</dt><dd>{fmt(audit.regime.p_bg)} МПа</dd>
                <dt>Давление на выкиде</dt><dd>{fmt(audit.regime.p_out)} МПа</dd>
              </dl>}
              {selectedNode.agg === aggregate && <>
                <dl>
                  <dt>Фактический КПД</dt><dd>{formatEfficiency(metrics.eta_unit)}</dd>
                  <dt>Номинальный КПД</dt><dd>{formatEfficiency(metrics.eta_nom)}</dd>
                </dl>
                <details><summary>Диагностика и потери</summary>
                  <dl>
                    <dt>Оценка КПД</dt><dd>{audit.quality.status === "unfit" ? "Данные непригодны для оценки" : audit.pump_assessment.name}</dd>
                    <dt>Коэффициент загрузки двигателя</dt><dd>{fmt(metrics.load_factor, 3)}</dd>
                    <dt>УРЭ фактический / расчётный</dt><dd>{fmt(metrics.sec_fact_kwh_m3, 3)} / {fmt(metrics.sec_calc_kwh_m3, 3)} кВт·ч/м³</dd>
                    {audit.quality.status !== "unfit" && <>
                      <dt>Потери по КПД</dt><dd>{fmt(audit.annual_summary.efficiency_energy_kwh, 0)} кВт·ч/год</dd>
                    </>}
                  </dl>
                </details>
              </>}
              <p className="muted sidebar-note">Измерения относятся только к выбранному агрегату и снимку.</p>
            </aside>}
          </div>
        </div>
        <p className="scheme-source">Источник схемы: {topology.source}</p>
      </>}
    </section>
  );
}
