import { LossesView } from "./LossesView";
import { OverviewView } from "../overview/OverviewView";
import { LinkButton } from "../../shared/ui/Button";
import type { Audit } from "../../shared/types";
import { useEffect } from "react";
import { Plot } from "../../charts/Plot";
import { timelineSignal } from "../monitoring/timeline.mjs";
import { segment, useResource } from "../../shared/api";
import { Panel } from "../../shared/ui/Panel";
import { Status } from "../../shared/ui/Status";
import { Tooltip } from "../../shared/ui/Tooltip";
import { Table } from "../../shared/ui/Table";
import { fmt } from "../../shared/ui/format";
import { EfficiencyKpiPanel } from "../overview/EfficiencyKpiPanel";
import { networkStages, stageDefinitions } from "./networkStages.mjs";
import {catalogMeasures,measureHref} from "./measureCatalog.mjs";
import {MeasureCards} from "./MeasureCards";
import "./networkLosses.css";

type Stage = "hall" | "pipes" | "wells";
type Component = { name: string; category: string; power_kw: number; basis: string; provenance: string };
type Network = {
  status: "scenario" | "infeasible" | "unavailable";
  total_loss_kw?: number | null;
  items?: Component[];
  warnings: string[];
  segments?: { id: string; pipeline_id: string; name: string; length_m: number; inner_diameter_mm: number; flow_m3h: number; pressure_loss_mpa: number; power_kw: number; source_sheet: string; source_row: number }[];
  wells?: { id: string; flow_m3h: number; well_loss_kw: number; armature_loss_kw: number; choke_loss_kw: number | null; required_pressure_mpa: number; available_pressure_mpa: number; deficit_mpa: number }[];
  measures?: { id: string; name: string; loss_name: string; description: string; saving_kw: number; saving_pct: number }[];
  assumptions?: { label: string; value: number | string | null; unit: string; provenance: string; basis: string }[];
  network?: { source_file: string; exported_at: string };
};
const origins: Record<string, string> = { measured: "Измерено", calculated: "Рассчитано", synthetic: "Синтетика" };

export function StageLosses({ stage, audit, inspectionKey }: { stage: Stage; audit: Audit; inspectionKey?:string }) {
  useEffect(() => { window.scrollTo({top:0,behavior:"instant"}); }, [stage]);
  const definition = stageDefinitions.find(item => item.id === stage)!;
  const objectId = audit.audit.object_id;
  const demo = objectId === "demo-ppd";
  const supported = objectId === "kns54an" || demo;
  const timestamp = audit.snapshot?.timestamp;
  const resource = useResource<Network>(
    supported && (audit.source === "field_trip" || timestamp)
      ? `/objects/${segment(objectId)}/aggregates/${segment(audit.audit.aggregate_id)}/network-losses` : null,
    JSON.stringify({ source: audit.source, ...(audit.source === "telemetry" && timestamp ? { day: timestamp.slice(0, 10), timestamp } : {}) }),
  );
  const data = resource.data;
  const summary = networkStages(data).find(item => item.id === stage);
  const components = summary ? (data?.items ?? []).filter(item => item.category === "потеря" && definition.names.includes(item.name)) : [];
  const annual=useResource<{annual:Parameters<typeof catalogMeasures>[0]}>(
    stage === "hall" && audit.quality.status !== "unfit" && (audit.source === "field_trip" || timestamp)
      ? `/objects/${segment(objectId)}/aggregates/${segment(audit.audit.aggregate_id)}/measures` : null,
    JSON.stringify({source:audit.source,...(audit.source === "telemetry" && timestamp ? {day:timestamp.slice(0,10),timestamp} : {})}),
  );
  const actions=catalogMeasures(annual.data?.annual ?? [],data).filter(action=>action.stage === stage).slice(0,3);
  const actionContext={objectId,aggregateId:audit.audit.aggregate_id,source:audit.source,timestamp:timestamp ?? ""};
  const aggregateLosses = audit.quality.status !== "unfit"
    ? audit.losses.filter(item => item.category === "потеря" && Number.isFinite(item.power_kw) && item.power_kw >= 0) : [];

  return <>
    {stage === "hall" && <div className="overview-primary machine-summary"><EfficiencyKpiPanel audit={audit} /></div>}
    {stage === "hall" && <><OverviewView audit={audit} /><LossesView audit={audit} inspectionKey={inspectionKey} /></>}
    <Panel title={stage === "hall" ? "Машинный блок" : definition.label} action={supported ? <span className="stage-basis">Сценарная оценка</span> : undefined}>
      <div className="network-losses stage-losses">
        {supported ? <Status {...resource} empty="Выберите режим агрегата для расчёта потерь." />
          : <p className="notice">Расчёт трубопроводов и скважин этого объекта ещё не подключён. Доли от потерь всей цепочки недоступны.</p>}
        {summary ? <>
          <dl className="network-balance-totals" aria-label="Итог выбранного участка">
            <div><dt>Потери участка</dt><dd>{fmt(summary.power_kw)} кВт</dd></div>
            <div><dt>Доля от всех потерь цепочки <Tooltip label="Доля потерь" content="Потери участка / сумма потерь всей цепочки. Полезная мощность в знаменатель не входит." /></dt><dd>{fmt(summary.share_pct, 1)} %</dd></div>
            <div><dt>Все потери цепочки</dt><dd>{fmt(data?.total_loss_kw)} кВт</dd></div>
          </dl>
          <Table rows={components.map(item => ({ ...item, percent: item.power_kw / data!.total_loss_kw! * 100, origin: origins[item.provenance] ?? item.provenance }))} columns={[
            { key: "name", label: "Составляющая" }, { key: "power_kw", label: "Потери, кВт" }, { key: "percent", label: "От всех потерь, %", digits: 1 }, { key: "origin", label: "Происхождение" }, { key: "basis", label: "Основание расчёта" },
          ]} />
        </> : data && <p className="notice" role="status">{data.status === "infeasible"
          ? "Доступного давления недостаточно: сбалансированная карта и доли потерь не построены."
          : "Баланс всей цепочки для выбранного режима недоступен. Доли потерь не рассчитаны."}</p>}
        <section aria-label="Мероприятия участка">
          <div className="network-section-heading"><h3>Мероприятия участка</h3><LinkButton href={measureHref(null,stage)}>Перейти к мероприятиям</LinkButton></div>
          {stage === "hall"&&<Status {...annual}/>}
          <MeasureCards actions={actions} context={actionContext}/>
          {!actions.length&&!annual.loading&&!resource.loading&&<p className="muted">Для этого участка применимые мероприятия не рассчитаны.</p>}
        </section>
        {stage === "hall" && !summary && aggregateLosses.length > 0 && <section aria-label="Потери агрегата до БГ"><h3>Агрегат и обвязка до блока гребёнок</h3>
          <p className="muted">Расчёт по выбранному режиму. Полная цепочка пока не рассчитана, поэтому доли от её потерь не показаны.</p>
          <Table rows={aggregateLosses} columns={[{ key: "name", label: "Составляющая" }, { key: "power_kw", label: "Потери, кВт" }]} />
        </section>}
        {stage === "pipes" && data?.segments?.length ? <section aria-label="Потери по участкам трубопроводов"><h3>Участки трубопроводов</h3>
          <p className="muted">Общие участки учтены один раз. Расход выбранного агрегата распределён по всей сети; совместная работа насосов не моделируется.</p>
          <Table rows={data.segments.map(item => ({ ...item, source: `${item.source_sheet}, строка ${item.source_row}` }))} columns={[
            { key: "pipeline_id", label: "Трубопровод" }, { key: "name", label: "Участок" }, { key: "length_m", label: "Длина, м" }, { key: "inner_diameter_mm", label: "Диаметр, мм" }, { key: "flow_m3h", label: "Расход, м³/ч" }, { key: "pressure_loss_mpa", label: "Потери давления, МПа", digits: 3 }, { key: "power_kw", label: "Потери, кВт" }, { key: "source", label: "Источник геометрии" },
          ]} />
        </section> : null}
        {stage === "wells" && data?.wells?.length ? <section aria-label="Потери по скважинам"><h3>Скважины и арматура</h3>
          <Table rows={data.wells} rowHighlighted={row => Number(row.deficit_mpa) > 0} columns={[
            { key: "id", label: "Скважина" }, { key: "flow_m3h", label: "Расход, м³/ч" }, { key: "well_loss_kw", label: "Трение в стволе, кВт" }, { key: "armature_loss_kw", label: "Арматура, кВт" }, { key: "choke_loss_kw", label: "Штуцирование, кВт" }, { key: "required_pressure_mpa", label: "Требуется, МПа" }, { key: "available_pressure_mpa", label: "Доступно, МПа" }, { key: "deficit_mpa", label: "Дефицит, МПа" },
          ]} />
        </section> : null}
        {data && <details className="stage-assumptions"><summary>Исходные данные и допущения</summary>
          {supported && <p className="muted">{demo ? "Режимы и потери демонстрационного объекта синтетические." : "Сценарная оценка выбранного агрегата. Геометрия из АРМИТС; единицы требуют подтверждения. Недостающие параметры и распределение расхода заменены синтетикой."}</p>}
          {data.warnings.length > 0 && <ul>{data.warnings.map((warning,index) => <li key={index}>{warning}</li>)}</ul>}
          {Boolean(data.assumptions?.length) && <Table rows={data.assumptions!.map(item => ({ ...item, origin: origins[item.provenance] ?? item.provenance }))} columns={[
          { key: "label", label: "Параметр" }, { key: "value", label: "Значение" }, { key: "unit", label: "Единица" }, { key: "origin", label: "Происхождение" }, { key: "basis", label: "Основание" },
        ]} />}
          {data.network && <p className="muted">Источник сети: {data.network.source_file} · выгрузка {data.network.exported_at}.</p>}
        </details>}
      </div>
    </Panel>
    {stage === "hall" && <>
      <Panel title="Режим машинного блока"><Table rows={[
        {name:"Напор",value:audit.audit.metrics.h_fact_m,unit:"м"},
        {name:"Подача",value:audit.audit.metrics.flow_m3h,unit:"м³/ч"},
        {name:"Электрическая мощность",value:audit.audit.metrics.p_electric_kw,unit:"кВт"},
        {name:"Гидравлическая мощность",value:audit.audit.metrics.p_hydraulic_kw,unit:"кВт"},
      ]} columns={[{key:"name",label:"Показатель"},{key:"value",label:"Значение"},{key:"unit",label:"Единица"}]} /></Panel>
      <EfficiencyHistory audit={audit} />
    </>}
  </>;
}

function EfficiencyHistory({audit}:{audit:Audit}) {
  const end = audit.snapshot?.timestamp.slice(0,10) ?? new Intl.DateTimeFormat("sv-SE",{timeZone:"Europe/Moscow"}).format(new Date());
  const first = new Date(`${end}T00:00:00Z`);
  first.setUTCDate(first.getUTCDate()-29);
  const start = first.toISOString().slice(0,10);
  const history = useResource<{points:{timestamp:string;efficiency:number|null;nominal_efficiency:number|null;basis:string}[]}>(`/objects/${segment(audit.audit.object_id)}/timeline?aggregate_id=${segment(audit.audit.aggregate_id)}&start=${start}&end=${end}`);
  const points = (history.data?.points ?? []).filter(point => !audit.snapshot || point.timestamp <= audit.snapshot.timestamp);
  return <Panel title="История КПД машинного блока" caption="Последние 30 дней до выбранного режима. Пропуски измерений не заполняются.">
    <Status {...history} />
    {points.some(point => point.efficiency != null) ? <Plot title="КПД агрегата" data={["efficiency","nominal_efficiency"].map(key => {
      const signal = timelineSignal(points,key,2);
      return {type:"scatter",mode:"lines",name:key === "efficiency" ? "КПД факт" : "КПД паспортный",x:signal.map(p=>p.timestamp),y:signal.map(p=>p.value == null ? null : p.value*100)};
    })} layout={{xaxis:{type:"date"},yaxis:{title:{text:"%"}}}} /> : history.data && <p className="muted">Истории КПД для выбранного периода нет.</p>}
  </Panel>;
}
