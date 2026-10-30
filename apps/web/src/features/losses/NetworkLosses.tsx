import {lossLabel,lossLabels} from "../../shared/lossLabels";
import { useState, type FormEvent } from "react";
import type { OperatorBalance } from "../scheme/LossFlow";
import { chainLossGroups } from "../../pages/lossChartData.mjs";
import type { Audit } from "../../shared/types";
import { segment, useResource } from "../../shared/api";
import { Button, LinkButton } from "../../shared/ui/Button";
import { Panel } from "../../shared/ui/Panel";
import { Status } from "../../shared/ui/Status";
import { Table } from "../../shared/ui/Table";
import { fmt } from "../../shared/ui/format";
import { LossCharts, type Loss } from "./LossCharts";
import {networkMeasures,scenarioParameters as parameters,readNetworkScenario,hydraulicLossMap} from "./networkScenario.mjs";
import {catalogMeasures,measureHref} from "./measureCatalog.mjs";
import {MeasureCards} from "./MeasureCards";
import { networkStages,stageDefinitions } from "./networkStages.mjs";
import "./networkLosses.css";

type Provenance = "calculated" | "synthetic" | "measured";
const origins: Record<Provenance, string> = { calculated: "Рассчитано", synthetic: "Синтетика", measured: "Измерено" };
type Scenario = Record<(typeof parameters)[number]["key"], number>;
type Intervention = "reduce_head" | "clean_pipes" | "reduce_local_resistance";
type NetworkMeasure = { id: Intervention; name: string; loss_name: string; description: string; saving_kw: number; saving_pct: number; baseline_input_kw: number; after_input_kw: number; required_pressure_mpa: number; options: Record<string, number>; assumptions: string[] };
type NetworkResponse = {
  status: "scenario" | "infeasible";
  title: string;
  input_kw: number;
  useful_kw: number | null;
  operator_balance?: OperatorBalance|null;
  total_loss_kw: number | null;
  balance_error_kw: number | null;
  items: (Loss & { provenance: Provenance; basis: string })[];
  segments: { id: string; pipeline_id: string; name: string; length_m: number; inner_diameter_mm: number; flow_m3h: number; pressure_loss_mpa: number; power_kw: number; provenance: Provenance; basis: string; source_sheet: string; source_row: number }[];
  wells: { id: string; flow_m3h: number; pipe_loss_kw: number; well_loss_kw: number; armature_loss_kw: number; choke_loss_kw: number | null; useful_kw: number; required_pressure_mpa: number; available_pressure_mpa: number; deficit_mpa: number; deficit_kw: number; synthetic_connection: boolean }[];
  assumptions: { parameter: string; label: string; value: number | string | null; unit: string; provenance: Provenance; basis: string }[];
  warnings: string[];
  network: { pipeline_count: number; segment_count: number; well_count: number; total_length_m?: number; source_file: string; exported_at: string };
  runtime_reading?: { hours: number; as_of: string; basis: string } | null;
  measures?: NetworkMeasure[];

} | { status: "unavailable"; warnings: string[]; measures?: NetworkMeasure[]; runtime_reading?: { hours: number; as_of: string; basis: string } | null };

export function NetworkLosses({ audit, view = "map" }: { audit: Audit; view?: "map" | "scenario" }) {
  const editable = view === "scenario";
  const [scenario, setScenario] = useState<Scenario>(() => readNetworkScenario(new URL(location.href).searchParams.get("network_scenario")) ?? Object.fromEntries(parameters.map(p => [p.key, p.value])));
  const [mode, setMode] = useState<"decomposition" | "percentage">("decomposition");
  const [detailed,setDetailed]=useState(false);
  const [selectedName, setSelectedName] = useState("");
  const demo = audit.audit.object_id === "demo-ppd";
  const timestamp = audit.snapshot?.timestamp;
  const resource = useResource<NetworkResponse>(
    audit.source === "field_trip" || timestamp
      ? `/objects/${segment(audit.audit.object_id)}/aggregates/${segment(audit.audit.aggregate_id)}/network-losses` : null,
    JSON.stringify({ source: audit.source, ...(audit.source === "telemetry" && timestamp ? { day: timestamp.slice(0, 10), timestamp } : {}), ...(editable ? {scenario} : {}) }),
  );
  const data = resource.data;
  const bgPower=data?.status === "scenario" ? data.operator_balance?.bg_kw : undefined;
  const physicalItems=data && data.status !== "unavailable" ? data.items.flatMap(item=>
    item.name === "Гидравлика насос→БГ" && typeof bgPower === "number" && Number.isFinite(bgPower)
      ? [item,{name:"Гидравлическая мощность на БГ",power_kw:bgPower,share:bgPower/data.input_kw,category:"промежуточная"}]
      : [item]) : [];
  const boreIndex=physicalItems.findIndex(item=>item.name === "Трение в стволах скважин");
  const chokeIndex=physicalItems.findIndex(item=>item.name === "Штуцирование скважин");
  if(boreIndex>=0 && chokeIndex>boreIndex) physicalItems.splice(chokeIndex,0,...physicalItems.splice(boreIndex,1));
  const balance=data?.status === "scenario" ? data.operator_balance : null;
  const summaryItems=chainLossGroups(balance);
  const grouped=!editable && !detailed && summaryItems.length>0;
  const hydraulic=hydraulicLossMap(data);
  const chartItems=editable ? hydraulic?.losses ?? [] : grouped ? summaryItems : physicalItems;
  const groups=grouped && balance ? [
    {id:"hall",label:"Машинный блок и обвязка до БГ",names:balance.groups.find(group=>group.id === "hall")!.children.map(child=>child.name)},
    {id:"pipes",label:"От БГ до устьев скважин",names:["Потери в трубопроводах","Штуцирование нагнетательных скважин"]},
  ] : editable ? stageDefinitions.filter(stage=>stage.id!=="hall") : stageDefinitions;
  const stages=grouped && balance ? groups.map(stage=>{
    const power=balance.groups.filter(group=>group.id === stage.id || stage.id === "pipes" && group.id === "wells").reduce((sum,group)=>sum+group.power_kw,0);
    return {id:stage.id,label:stage.label,power_kw:power,share_pct:power/balance.input_kw*100};
  }) : editable && hydraulic ? networkStages({...data,status:"scenario",items:hydraulic.losses,total_loss_kw:hydraulic.total_loss_kw}).filter(stage=>stage.id!=="hall").map(stage=>({...stage,share_pct:stage.power_kw/hydraulic.input_kw*100})) : networkStages(data);
  const selected = data && data.status !== "unavailable" ? data.items.find(item => item.name === selectedName) : undefined;
  const measures = networkMeasures(data?.status ?? "", data?.measures ?? [], selectedName);
  const actionContext={objectId:audit.audit.object_id,aggregateId:audit.audit.aggregate_id,source:audit.source,timestamp:timestamp ?? "",networkScenario:scenario};
  const actions=catalogMeasures([],{status:data?.status ?? "",measures});
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setScenario(Object.fromEntries(parameters.map(p => [p.key, Number(form.get(p.key))])) as Scenario);
    setSelectedName("");
  };
  return <Panel title={editable ? "Гидравлический сценарий" : "Карта потерь по цепочке"} action={!editable ? <LinkButton href="#network-scenario">Гидравлический сценарий</LinkButton> : undefined}>
    <div className="network-losses">
      {editable && <p className="notice">{demo ? "Демонстрационный объект: геометрия, режимы и потери синтетические. Не производственные данные." : "Геометрия — из АРМИТС; единицы выгрузки ещё требуют подтверждения. Недостающие параметры и распределение потока заменены синтетикой. Это сценарная оценка, а не измеренные потери или достигнутая экономия."}</p>}
      {editable && <details className="network-scenario">
        <summary>Параметры сценария</summary>
        <form onSubmit={submit}>
          <div className="network-scenario-fields">{parameters.map(p => <label key={p.key}>
            <span>{p.label}</span>
            <input aria-label={p.label} name={p.key} type="number" required min={p.min} max={p.max} step={p.step} defaultValue={scenario[p.key]} />
            <small>Синтетическое значение</small>
          </label>)}</div>
          <p className="muted">Полезное давление задано в поверхностном эквиваленте без перепада высот; высоты учитываются отдельно. Положительный перепад — подъём от станции. Длина ствола используется только для расчёта трения.</p>
          <Button type="submit" loading={resource.loading}>Пересчитать сценарий</Button>
        </form>
      </details>}
      <Status {...resource} empty="Для расчёта выберите режим агрегата." />
      {data && <>
        {data.status !== "unavailable" && <>
          <p className="muted">{editable ? "Сценарный баланс внешней сети от блока гребёнок." : data.title}</p>
          <p className="network-metadata">{data.network.well_count} скважин · {fmt((data.network.total_length_m ?? [...new Map(data.segments.map(item => [item.id, item])).values()].reduce((sum, item) => sum + item.length_m, 0)) / 1000, 1)} км учтённых участков · перепад высот {fmt(scenario.elevation_change_m, 0)} м (синтетика). {demo ? "Геометрия синтетическая, длины в метрах и диаметры в миллиметрах." : "Геометрия по реестру, единицы не подтверждены."}</p>
        </>}
        {data.warnings.length > 0 && (data.status === "unavailable"
          ? <div className="notice" role="status"><ul>{data.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>
          : <details><summary>Ограничения и принятые соединения ({data.warnings.length})</summary><ul>{data.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>)}
        {data.status === "unavailable" ? <p className="notice error" role="alert">{editable ? "Гидравлический сценарий недоступен для выбранного режима." : "Карта всей цепочки недоступна для выбранного режима."}</p> : <>
        {data.status === "scenario" && (!editable || hydraulic) ? <>
          <dl className="network-balance-totals">
            {!editable && <div><dt>{lossLabels.input}</dt><dd>{fmt(data.input_kw)} кВт</dd></div>}
            <div><dt>{lossLabels.bg}</dt><dd>{fmt(bgPower)} кВт</dd></div>
            <div><dt>{editable ? "Потери от БГ" : "Потери всей цепочки"}</dt><dd>{fmt(editable ? hydraulic?.total_loss_kw : grouped ? balance?.total_loss_kw : data.total_loss_kw)} кВт</dd></div>
            <div><dt>{grouped ? lossLabels.output : lossLabels.useful}</dt><dd>{fmt(editable ? hydraulic?.useful_kw : grouped ? balance?.output_kw : data.useful_kw)} кВт</dd></div>
            <div><dt>Невязка баланса</dt><dd>{fmt(editable ? hydraulic?.balance_error_kw : grouped && balance ? balance.input_kw-balance.total_loss_kw-balance.output_kw : data.balance_error_kw !== null && Math.abs(data.balance_error_kw) < 1e-9 ? 0 : data.balance_error_kw, 3)} кВт</dd></div>
          </dl>
          <dl className="network-balance-totals" aria-label={editable ? "Потери по участкам внешней сети" : "Потери по участкам цепочки"}>
            {stages.map(stage => <div key={stage.id}><dt>{stage.label}</dt><dd>{fmt(stage.power_kw)} кВт · {fmt(stage.share_pct,1)} % {editable ? "мощности на БГ" : grouped ? "потребления" : "потерь"}</dd></div>)}
          </dl>
          <div className="metric-toolbar"><div className="metric-segments" role="group" aria-label="Представление всей цепочки">
            <button type="button" aria-pressed={mode === "decomposition"} onClick={() => setMode("decomposition")}>Разложение</button>
            <button type="button" aria-pressed={mode === "percentage"} onClick={() => setMode("percentage")}>Структура, %</button>
          </div>
            {!editable && summaryItems.length>0 && <Button variant="secondary" aria-expanded={detailed} onClick={()=>{setDetailed(previous=>!previous);setSelectedName("");}}>{detailed ? "Свернуть детализацию" : "Детализация"}</Button>}
          </div>
          <p className="stage-basis">{editable ? "Граница расчёта — от БГ через трубопроводы, штуцеры и стволы скважин. Доли показаны от гидравлической мощности на БГ. Машинный блок в эту карту не входит." : grouped ? "Граница расчёта — устья после штуцеров. Трение в НКТ доступно в детализации." : "Подробный баланс включает трение в стволах скважин до полезной закачки."}</p>
          {mode === "decomposition" ? <>
            <div className="network-waterfall-scroll" tabIndex={0} role="region" aria-label="Разложение всей цепочки, горизонтальная прокрутка">
              <div className="network-waterfall-wide"><LossCharts power={editable ? hydraulic?.input_kw ?? 0 : data.input_kw} inputLabel={editable ? lossLabels.bg : undefined} losses={chartItems} mode={mode} showSummary={false} groups={groups} onSelect={setSelectedName} /></div>
            </div>
            <p className="muted network-waterfall-hint">На узком экране прокрутите график вправо; доступны стрелки клавиатуры.</p>
          </> : <LossCharts power={editable ? hydraulic?.input_kw ?? 0 : data.input_kw} inputLabel={editable ? lossLabels.bg : undefined} losses={chartItems} mode={mode} showSummary={false} onSelect={setSelectedName} />}
          {selected && <p><strong>{lossLabel(selected.name)}: {fmt(selected.power_kw)} кВт.</strong> {selected.basis} Происхождение: {origins[selected.provenance]}.</p>}
        </> : <p className="notice error" role="alert">{data.status === "infeasible" ? "Сценарий физически невыполним: доступного давления недостаточно. Сбалансированная карта не построена." : editable ? "Гидравлический сценарий недоступен: нет положительной мощности на БГ." : "Карта всей цепочки недоступна для выбранного режима."}</p>}
        {editable && <>
        {data.items.length > 0 && <details><summary>Составляющие и основания расчёта</summary><Table rows={(editable ? hydraulic?.losses ?? [] : data.items).map(item => ({ ...item, name:lossLabel(item.name), origin: "provenance" in item ? origins[item.provenance as Provenance] : "Рассчитано", percent: item.share * 100 }))} columns={[
          { key: "name", label: "Составляющая" }, { key: "power_kw", label: "Мощность, кВт" }, { key: "percent", label: "Доля, %" }, { key: "origin", label: "Происхождение" }, { key: "basis", label: "Основание" },
        ]} /></details>}
        <details><summary>Трубопроводы: {data.network.pipeline_count} · участки: {data.network.segment_count}</summary>
          <p className="muted">Общие участки учитываются один раз. В сценарии работает только выбранный агрегат: его расход распределяется по всей сети, остальные насосы выключены. Это не оценка его вклада при совместной работе агрегатов.</p>
          <Table rows={data.segments.map(row => ({ ...row, origin: origins[row.provenance], source: `${row.source_sheet}, строка ${row.source_row}` }))} columns={[
            { key: "pipeline_id", label: "Трубопровод" }, { key: "name", label: "Участок" }, { key: "length_m", label: "Длина, м" }, { key: "inner_diameter_mm", label: "Внутренний диаметр, мм" }, { key: "flow_m3h", label: "Расход, м³/ч" }, { key: "pressure_loss_mpa", label: "Потери давления, МПа", digits: 3 }, { key: "power_kw", label: "Потери, кВт" }, { key: "origin", label: "Происхождение" }, { key: "source", label: "Источник геометрии" },
          ]} />
        </details>
        <details open={data.status === "infeasible"}><summary>Скважины: {data.network.well_count}</summary>
          <Table rows={data.wells.map(row => ({ ...row, connection: row.synthetic_connection ? "Синтетическая" : "По реестру" }))} rowHighlighted={row => Number(row.deficit_kw) > 0} columns={[
            { key: "id", label: "Скважина" }, { key: "flow_m3h", label: "Расход, м³/ч" }, { key: "pipe_loss_kw", label: "Трубы по пути, кВт" }, { key: "well_loss_kw", label: `${lossLabels.bore}, кВт` }, { key: "armature_loss_kw", label: `${lossLabels.local}, кВт` }, { key: "choke_loss_kw", label: `${lossLabels.choke}, кВт` }, { key: "useful_kw", label: `${lossLabels.useful}, кВт` }, { key: "required_pressure_mpa", label: "Требуется, МПа" }, { key: "available_pressure_mpa", label: "Доступно, МПа" }, { key: "deficit_mpa", label: "Дефицит, МПа" }, { key: "deficit_kw", label: "Дефицит, кВт" }, { key: "connection", label: "Связь с сетью" },
          ]} />
          <p className="muted">Потери труб по пути к скважинам могут включать общие участки: этот столбец нельзя суммировать. Итог сети рассчитан по уникальным участкам.</p>
        </details>
        <details><summary>Исходные данные и допущения</summary><Table rows={data.assumptions.map(row => ({ ...row, origin: origins[row.provenance] }))} columns={[
          { key: "label", label: "Параметр" }, { key: "value", label: "Значение" }, { key: "unit", label: "Единица" }, { key: "origin", label: "Происхождение" }, { key: "basis", label: "Основание" },
        ]} /></details>
        <p className="muted">Источник сети: {data.network.source_file} · выгрузка {data.network.exported_at}.</p>
        {data.status === "scenario" && hydraulic && <section className="network-actions" aria-label="Мероприятия внешней сети">
          <div className="network-section-heading">
            <h3>{selected ? "Мероприятия по выбранной составляющей" : "Мероприятия внешней сети"}</h3>
            {selectedName && <Button variant="secondary" onClick={() => setSelectedName("")}>Все мероприятия</Button>}
          </div>
          {!selected && <p className="muted">Выберите составляющую на графике для разбора.</p>}
          <p className="muted">Расчёт и сравнение доступны в разделе «Мероприятия». Эффекты альтернативных мероприятий не суммируются.</p>
          <div className="content-actions"><LinkButton href={measureHref(null,'pipes',actionContext)}>Перейти к мероприятиям</LinkButton></div>
          <MeasureCards actions={actions} context={actionContext}/>
          {!actions.length && <p className="notice">Для выбранной составляющей и заданных параметров применимые мероприятия не рассчитаны.</p>}
        </section>}
        </>}
        </>}
        {editable && data.runtime_reading && <p className="notice">Накопленная наработка {audit.audit.aggregate_id}: {fmt(data.runtime_reading.hours, 0)} ч, на {data.runtime_reading.as_of}. {data.runtime_reading.basis}</p>}
      </>}
    </div>
  </Panel>;
}
