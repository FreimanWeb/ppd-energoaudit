import { LinkButton } from "../../shared/ui/Button";
import { segment, useResource } from "../../shared/api";
import { Status } from "../../shared/ui/Status";
import { inspections, inspectionFor, inspectionHref, relatedMeasures } from "../inspection/inspection.mjs";
import "../inspection/inspection.css";
import { useEffect, useState } from "react";
import type { Audit } from "../../shared/types";
import { dashboardData } from "../overview/dashboardData.mjs";
import { LossCharts } from "./LossCharts";
import { Panel } from "../../shared/ui/Panel";
import { Table } from "../../shared/ui/Table";
import { fmt } from "../../shared/ui/format";

export function LossesView({ audit, inspectionKey }: { audit: Audit; inspectionKey?: string }) {
  const [mode, setMode] = useState<"decomposition" | "flow" | "percentage">("decomposition");
  const view = dashboardData(audit);
  const [nameChoice, setName] = useState("");
  useEffect(() => setName(""), [inspectionKey]);
  const selectedName = nameChoice || inspectionFor(inspectionKey)?.loss || "";
  const selected = view.losses.find((item: Audit["losses"][number]) => item.name === selectedName);
  const metric = nameChoice ? Object.entries(inspections).find(([key, item]) => key.endsWith("_loss") && item.loss === nameChoice)?.[0] : inspectionKey;
  const addresses = inspectionFor(metric)?.addresses ?? [];
  const timestamp = audit.snapshot?.timestamp;
  const proposals = useResource<{ annual: { measure_id: string; name: string; addresses?: string; money_saving_krub: number; cls: string }[] }>(
    view.usable && addresses.length > 0 && (audit.source === "field_trip" || timestamp)
      ? `/objects/${segment(audit.audit.object_id)}/aggregates/${segment(audit.audit.aggregate_id)}/measures` : null,
    JSON.stringify({source: audit.source, basis: "annual", ...(audit.source === "telemetry" && timestamp ? {day: timestamp.slice(0, 10), timestamp} : {})}),
  );
  const measures = relatedMeasures(proposals.data?.annual ?? [], metric);
  return (
    <>
    <Panel title="Агрегат и обвязка до блока гребёнок" caption="Разложение мощности выбранного НА. Полезная мощность — на выходе блока гребёнок, до внешних трубопроводов и скважин." help={`${view.runtime} Годовая наработка: ${fmt(audit.scope.annual_runtime_hours)} ч; тариф ${fmt(audit.tariff)} ₽/кВт·ч. Выберите элемент графика, чтобы увидеть доступные мероприятия.`}>
      {view.usable ? (
        <>
          {view.losses.length > 0 && <div className="metric-toolbar">
            <div className="metric-segments" role="group" aria-label="Представление карты потерь">
              <button type="button" aria-pressed={mode === "decomposition"} onClick={() => setMode("decomposition")}>Разложение</button>
              <button type="button" aria-pressed={mode === "flow"} onClick={() => setMode("flow")}>Поток мощности</button>
              <button type="button" aria-pressed={mode === "percentage"} onClick={() => setMode("percentage")}>Структура, %</button>
            </div>
          </div>}
          <LossCharts onSelect={name => { if (view.losses.some((item: Audit["losses"][number]) => item.name === name)) setName(name); }} power={audit.audit.metrics.p_electric_kw ?? 0} losses={view.losses} status={audit.quality.status} mode={mode} />
          {selectedName && <section className="inspection-result" aria-label="Разбор составляющей">
            <header className="loss-selection-heading"><h3>{selectedName}</h3>
              {metric && <nav aria-label="Основание составляющей">
                <LinkButton href={inspectionHref("sources", metric)}>Источники</LinkButton>
                <LinkButton href={inspectionHref("formulas", metric)}>Формулы</LinkButton>
              </nav>}
            </header>
            {selected ? <p>{fmt(selected.power_kw)} кВт · {fmt(selected.share * 100, 2)}% подведённой мощности.</p>
              : <p className="notice">Эта составляющая разложения недоступна в выбранном режиме. Годовая оценка и возможные мероприятия имеют отдельное расчётное основание.</p>}
            {(selected?.category === "потеря" || addresses.length > 0) && <section className="loss-measures" aria-label="Предлагаемые мероприятия">
              <header><h4>Что можно изменить</h4>{measures.length > 0 && <LinkButton href={inspectionHref("measures", metric)}>Оценить мероприятия</LinkButton>}</header>
              {addresses.length > 0 && <Status {...proposals} empty="Нет данных для оценки мероприятий." />}
              {measures.length > 0 ? <ul>{measures.map(measure => <li key={measure.measure_id}>
                <div><span>{measure.name}</span><small>{measure.cls === "сценарная оценка" ? "Сценарий · CAPEX требует оценки" : measure.cls}</small></div>
                <div className="loss-measure-effect"><strong>{fmt(measure.money_saving_krub, 1)} тыс. ₽/год</strong><small>Расчётный эффект</small></div>
              </li>)}</ul> : !proposals.loading && !proposals.error && (addresses.length === 0 || proposals.data) && <p className="muted">Для выбранной составляющей мероприятия пока не предложены.</p>}
            </section>}
          </section>}
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
    </>
  );
}
