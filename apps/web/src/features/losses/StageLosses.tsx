import {lossLabels} from "../../shared/lossLabels";
import {PipelineLosses,type PipelineSegment,type PipelineWell} from "./PipelineLosses";
import { MachineLossMap } from "./MachineLossMap";
import { LossDetailPanel, lossDetailKey } from "./LossDetailPanel";
import { readNetworkScenario } from "./networkScenario.mjs";
import { OverviewView } from "../overview/OverviewView";
import { LinkButton } from "../../shared/ui/Button";
import { inspectionFor } from "../inspection/inspection.mjs";
import type { Audit } from "../../shared/types";
import type { PageProps } from "../../shared/ui/context";
import { contextBody } from "../../shared/ui/context";
import type { OperatorBalance } from "../scheme/LossFlow";
import { useEffect } from "react";
import { Plot } from "../../charts/Plot";
import { timelineSignal } from "../monitoring/timeline.mjs";
import { segment, useResource } from "../../shared/api";
import { Panel } from "../../shared/ui/Panel";
import { Status } from "../../shared/ui/Status";
import { Table } from "../../shared/ui/Table";
import { useWellSelection, WellLinks } from "../../shared/wellSelection";
import { stageDefinitions } from "./networkStages.mjs";
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
  segments?: PipelineSegment[];
  wells?: (PipelineWell & {well_loss_kw:number})[];
  measures?: { id: string; name: string; loss_name: string; description: string; saving_kw: number; saving_pct: number }[];
  assumptions?: { label: string; value: number | string | null; unit: string; provenance: string; basis: string }[];
  network?: { source_file: string; exported_at: string };
  operator_balance?: OperatorBalance | null;
};
const origins: Record<string, string> = { measured: "Измерено", calculated: "Рассчитано", synthetic: "Синтетика" };

export function StageLosses({ stage, audit, context, inspectionKey, view="indicators", hasNetwork=false, isExample=false }: { stage: Stage; audit: Audit; context: PageProps; inspectionKey?:string; view?:"indicators"|"map"; hasNetwork?:boolean; isExample?:boolean }) {
  useEffect(() => { window.scrollTo({top:0,behavior:"instant"}); }, [stage]);
  const selectedWell = useWellSelection();
  const definition = stageDefinitions.find(item => item.id === stage)!;
  const objectId = audit.audit.object_id;
  const supported = hasNetwork;
  const timestamp = audit.snapshot?.timestamp;
  // Физический разбор участка не требует сценария всей сети; сетевые таблицы ниже БГ — требуют.
  const needsNetwork=stage!=="hall";
  const rawScenario = needsNetwork ? new URL(location.href).searchParams.get("network_scenario") : null;
  const scenario = rawScenario ? readNetworkScenario(rawScenario) : null;
  const invalidScenario = Boolean(rawScenario && !scenario);
  const resource = useResource<Network>(
    needsNetwork && !invalidScenario && supported && (audit.source === "field_trip" || timestamp)
      ? `/objects/${segment(objectId)}/aggregates/${segment(audit.audit.aggregate_id)}/network-losses` : null,
    contextBody(context, scenario ? {scenario} : {}),
  );
  const data = resource.data;
  const actions=catalogMeasures([],data).filter(action=>action.stage === stage).slice(0,3);
  const actionContext={objectId,aggregateId:audit.audit.aggregate_id,source:audit.source,timestamp:timestamp ?? ""};
  const chainInspection=inspectionFor(inspectionKey);
  const foreignStage=chainInspection?.stage ?? (chainInspection?.loss ? "hall" : undefined);
  const foreign=foreignStage && foreignStage!==stage ? stageDefinitions.find(item=>item.id===foreignStage) : undefined;
  const foreignNotice=foreign ? <p className="notice">Запрошенная составляющая относится к участку «{foreign.label}». Разбор открыт на её странице.</p> : null;
  const mappedKey=lossDetailKey(inspectionKey);
  const detailKey=foreign ? stage : (mappedKey ?? stage);
  const stageActions=<section aria-label="Мероприятия участка">
          <div className="network-section-heading"><h3>Мероприятия участка</h3><LinkButton href={measureHref(null,stage)}>Перейти к мероприятиям</LinkButton></div>
          <MeasureCards actions={actions} context={actionContext}/>
          {!actions.length&&<p className="muted">Для этого участка применимые мероприятия не рассчитаны.</p>}
        </section>;
  const downstreamContent=needsNetwork ? <>
        {supported ? <Status {...resource} empty="Выберите режим агрегата для расчёта потерь." />
          : <p className="notice">Расчёт трубопроводов и скважин этого объекта ещё не подключён. Сводка участка ниже показана по доступным данным.</p>}
        {stage === "pipes" && data && data.status !== "unavailable" && Boolean(data.segments?.length || data.wells?.length) && <PipelineLosses segments={data.segments ?? []} wells={data.wells ?? []}/>}
        {stage === "wells" && data?.wells?.length ? <section aria-label="Потери по скважинам"><h3>Скважины</h3>
          {selectedWell && !data.wells.some(well=>well.id===selectedWell) && <p className="notice">Скважина {selectedWell} отсутствует в этом сценарии. Показаны все скважины сценария; выбор сохранён для архива и CRM.</p>}
          <Table rows={data.wells} rowHighlighted={row => row.id === selectedWell || Number(row.deficit_mpa) > 0} columns={[
            { key: "id", label: "Скважина" }, {key:"inspect",label:"Подробнее",render:row=><WellLinks code={String(row.id)}/>}, { key: "flow_m3h", label: "Расход, м³/ч" }, { key: "well_loss_kw", label: `${lossLabels.bore}, кВт` }, { key: "armature_loss_kw", label: `${lossLabels.local}, кВт` }, { key: "choke_loss_kw", label: `${lossLabels.choke}, кВт` }, { key: "required_pressure_mpa", label: "Требуется, МПа" }, { key: "available_pressure_mpa", label: "Доступно, МПа" }, { key: "deficit_mpa", label: "Дефицит, МПа" },
          ]} />
        </section> : null}
        {data && <details className="stage-assumptions"><summary>Исходные данные и допущения сценария</summary>
          {supported && <p className="muted">{isExample ? "Режимы и потери демонстрационного объекта синтетические." : "Сценарная оценка выбранного агрегата. Геометрия из АРМИТС; единицы требуют подтверждения. Недостающие параметры и распределение расхода заменены синтетикой."}</p>}
          {data.warnings.length > 0 && <ul>{data.warnings.map((warning,index) => <li key={index}>{warning}</li>)}</ul>}
          {Boolean(data.assumptions?.length) && <Table rows={data.assumptions!.map(item => ({ ...item, origin: origins[item.provenance] ?? item.provenance }))} columns={[
          { key: "label", label: "Параметр" }, { key: "value", label: "Значение" }, { key: "unit", label: "Единица" }, { key: "origin", label: "Происхождение" }, { key: "basis", label: "Основание" },
        ]} />}
          {data.network && <p className="muted">Источник сети: {data.network.source_file} · выгрузка {data.network.exported_at}.</p>}
        </details>}
      </> : null;
  const stageContent=<div className="network-losses stage-losses">
        {foreignNotice}
        <LossDetailPanel context={context} focus={detailKey}/>
        {downstreamContent}
      </div>;
  if(stage==="hall"){
    if(view==="indicators") return <>
      <Panel title="Режим машинного блока"><Table rows={[
        {name:"Напор",value:audit.audit.metrics.h_fact_m,unit:"м"},
        {name:"Подача",value:audit.audit.metrics.flow_m3h,unit:"м³/ч"},
        {name:"Электрическая мощность",value:audit.audit.metrics.p_electric_kw,unit:"кВт"},
        {name:"Гидравлическая мощность",value:audit.audit.metrics.p_hydraulic_kw,unit:"кВт"},
      ]} columns={[{key:"name",label:"Показатель"},{key:"value",label:"Значение"},{key:"unit",label:"Единица"}]} /></Panel>
      <OverviewView audit={audit}/>
      {audit.source==="telemetry" && <EfficiencyHistory audit={audit}/>}
    </>;
    return <MachineLossMap context={context} inspectionKey={inspectionKey} unfit={audit.quality.status==="unfit"} issues={audit.quality.issues.map(issue=>issue.message)}/>;
  }
  return <Panel title={definition.label} action={supported ? <span className="stage-basis">Сценарная оценка сети ниже БГ</span> : undefined}>
      {stageContent}
      {stageActions}
    </Panel>;
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
