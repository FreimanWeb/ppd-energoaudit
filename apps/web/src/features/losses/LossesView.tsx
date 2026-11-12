import {lossLabel,lossLabels} from "../../shared/lossLabels";
import { Button, LinkButton } from "../../shared/ui/Button";
import { segment, useResource } from "../../shared/api";
import { Status } from "../../shared/ui/Status";
import { inspections, inspectionFor, inspectionHref, relatedMeasures } from "../inspection/inspection.mjs";
import "../inspection/inspection.css";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import type { Audit } from "../../shared/types";
import { contextBody, type PageProps } from "../../shared/ui/context";
import { dashboardData } from "../overview/dashboardData.mjs";
import { LossCharts } from "./LossCharts";
import { Panel } from "../../shared/ui/Panel";
import { Table } from "../../shared/ui/Table";
import { fmt } from "../../shared/ui/format";
import { aggregateLossGroups } from "../../pages/lossChartData.mjs";
import { lossDetailHref } from "./lossDetail.mjs";

export function LossesView({ audit, context, inspectionKey, summary, children }: { audit: Audit; context: PageProps; inspectionKey?: string; summary?:ReactNode; children?:ReactNode }) {
  const [mode, setMode] = useState<"decomposition" | "percentage">("decomposition");
  const view = dashboardData(audit);
  const [detailed,setDetailed]=useState(()=>Boolean(inspectionFor(inspectionKey)?.loss));
  useEffect(()=>{setDetailed(Boolean(inspectionFor(inspectionKey)?.loss));},[inspectionKey]);
  const grouped=aggregateLossGroups(view.losses);
  const losses:Audit["losses"]=detailed ? aggregateLossGroups(view.losses,true) : grouped;
  const canDetail=grouped !== view.losses;
  const labels:Record<string,string>=canDetail ? {"Полезная мощность":lossLabels.bg} : {};
  const label=(name:string)=>labels[name] ?? lossLabel(name);

  const [nameChoice, setName] = useState("");
  useEffect(() => setName(""), [inspectionKey]);
  const inspectedLoss=inspectionFor(inspectionKey)?.loss || "";
  const selectedName = nameChoice || (!detailed && ["Дросселирование","Гидравл. насос→БГ"].includes(inspectedLoss) ? "Потери на участке Насос–БГ" : inspectedLoss);
  const selected = losses.find((item: Audit["losses"][number]) => item.name === selectedName);
  const metric = nameChoice ? Object.entries(inspections).find(([key, item]) => key.endsWith("_loss") && item.loss === nameChoice)?.[0] : inspectionKey;
  const addresses = inspectionFor(metric)?.addresses ?? [];
  const timestamp = audit.snapshot?.timestamp;
  const proposals = useResource<{ annual: { measure_id: string; name: string; addresses?: string; money_saving_krub: number; cls: string }[] }>(
    view.usable && addresses.length > 0 && (audit.source === "field_trip" || timestamp)
      ? `/objects/${segment(audit.audit.object_id)}/aggregates/${segment(audit.audit.aggregate_id)}/measures` : null,
    contextBody(context, {basis: "annual"}),
  );
  const measures = relatedMeasures(proposals.data?.annual ?? [], metric);
  // Клик по столбцу потерь открывает страницу подробностей статьи; стабильная
  // ссылка не пересоздаёт модель графика при каждом рендере.
  const select = useCallback((name: string) => {
    const href = lossDetailHref(name, "machine-losses");
    if (href) location.assign(href); else setName(name);
  }, []);
  return (
    <>
    <Panel title="Цифровая карта потерь мощности" caption="Агрегат и обвязка до блока гребёнок. Разложение мощности выбранного НА." help={`${view.runtime} Годовая наработка: ${fmt(audit.scope.annual_runtime_hours)} ч; тариф ${fmt(audit.tariff)} ₽/кВт·ч. Нажмите на столбец, чтобы открыть подробности составляющей.`}>
      {view.usable ? (
        <>
          {summary}
          {view.losses.length > 0 && <div className="metric-toolbar">
            <div className="metric-segments" role="group" aria-label="Представление карты потерь">
              <button type="button" aria-pressed={mode === "decomposition"} onClick={() => setMode("decomposition")}>Разложение</button>
              <button type="button" aria-pressed={mode === "percentage"} onClick={() => setMode("percentage")}>Структура, %</button>
            </div>
            {canDetail && <Button variant="secondary" aria-expanded={detailed} onClick={()=>{setDetailed(previous=>!previous);setName("");}}>{detailed ? "Свернуть детализацию НА" : "Детализация потерь НА"}</Button>}
          </div>}
          <LossCharts onSelect={select} power={audit.audit.metrics.p_electric_kw ?? 0} losses={losses} status={audit.quality.status} mode={mode} axisLabels={labels} showSummary={false} />
          <p className="muted">Потреблённая мощность {fmt(audit.audit.metrics.p_electric_kw)} кВт · {canDetail ? "гидравлическая мощность на БГ" : "полезная мощность"} {fmt(losses.find(item=>item.category === "полезная")?.power_kw)} кВт.</p>
          {detailed && view.losses.some((item:Audit["losses"][number])=>item.name === "Потери КПД") && <p className="muted">Износ и неоптимальная подача в текущем расчёте не разделены: показана суммарная составляющая снижения КПД.</p>}
          {selectedName && <section className="inspection-result" aria-label="Разбор составляющей">
            <header className="loss-selection-heading"><h3>{label(selectedName)}</h3>
              {metric && <nav aria-label="Основание составляющей">
                <LinkButton href={inspectionHref("sources", metric)}>Источники</LinkButton>
                <LinkButton href={inspectionHref("formulas", metric)}>Формулы</LinkButton>
              </nav>}
            </header>
            {selected ? <p>{fmt(selected.power_kw)} кВт · {fmt(selected.share * 100, 2)}% потреблённой мощности.</p>
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
            rows={losses.map((loss: Audit["losses"][number]) => ({ ...loss, name:label(loss.name), percent: loss.share * 100 }))}
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
          {canDetail && <p className="muted">Примечание: расчёт выполнен для участка до БГ; потери далее по системе ППД здесь не учтены.</p>}
        </>
      ) : <p className="notice error">Карта потерь не построена: режим непригоден для экономических выводов.</p>}
      {children}
    </Panel>
    </>
  );
}
