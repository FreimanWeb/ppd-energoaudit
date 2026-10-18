import {useEffect,useState} from "react";
import {segment,useResource} from "../../shared/api";
import {contextBody,type PageProps} from "../../shared/ui/context";
import {Panel} from "../../shared/ui/Panel";
import {Status} from "../../shared/ui/Status";
import {Button,LinkButton} from "../../shared/ui/Button";
import {fmt} from "../../shared/ui/format";
import {stageDefinitions} from "./networkStages.mjs";
import {catalogMeasures,measureHref} from "./measureCatalog.mjs";
import {MeasureCards} from "./MeasureCards";

type Network={status:string;measures?:NonNullable<Parameters<typeof catalogMeasures>[1]>["measures"];comparison?:{
  name:string;saving_kw:number;before:{input_kw:number};after:{input_kw:number};assumptions:string[];
}|null};

export function ChainMeasures({context,annual,eligible,loading,error}: {
  context:PageProps;annual:Parameters<typeof catalogMeasures>[0];eligible:boolean;loading:boolean;error?:string;
}) {
  const [intervention,setIntervention]=useState<string|null>(null);
  const supported=["kns54an","demo-ppd"].includes(context.objectId);
  const path=`/objects/${segment(context.objectId)}/aggregates/${segment(context.aggregateId)}/network-losses`;
  const network=useResource<Network>(eligible&&supported ? path : null,contextBody(context));
  const comparison=useResource<Network>(eligible&&supported&&intervention ? path : null,contextBody(context,{intervention}));
  const params=new URL(location.href).searchParams;
  const stage=stageDefinitions.some(stage=>stage.id===params.get("stage")) ? params.get("stage")! : "";
  const id=params.get("measure") || "";
  const actions=catalogMeasures(annual,network.data);
  const rows=actions.filter(action=>!stage||action.stage===stage);
  const chosen=rows.find(action=>action.id===id);
  useEffect(()=>setIntervention(null),[id]);
  const result=chosen?.intervention === intervention && comparison.data?.status === "scenario" ? comparison.data.comparison : null;
  return <Panel title="Мероприятия по участкам">
    <div className="page-controls"><label>Участок<select aria-label="Участок мероприятий" value={stage} onChange={event=>{
      history.replaceState(null,"",measureHref(null,event.target.value));
      window.dispatchEvent(new PopStateEvent("popstate"));
    }}><option value="">Все участки</option>{stageDefinitions.map(stage=><option key={stage.id} value={stage.id}>{stage.id === "hall" ? "Машинный блок" : stage.label}</option>)}</select></label></div>
    <p className="muted">Годовая экономия и снижение мощности показаны раздельно. Эффекты альтернативных мероприятий не суммируются.</p>
    {loading&&<p className="muted">Загружаем мероприятия машинного блока…</p>}
    {error&&<p className="notice error" role="alert">{error}</p>}
    {supported&&eligible&&<Status {...network}/>}
    {!eligible&&<p className="notice">Для оценки мероприятий выберите пригодный режим.</p>}
    {chosen ? <section className="network-measure action-detail" aria-label="Мероприятие" data-action-id={chosen.id}>
      <div className="network-section-heading"><h3>{chosen.name}</h3><LinkButton href={measureHref(null,stage)}>К списку мероприятий</LinkButton></div>
      <p>{chosen.description}</p>
      <dl className="network-balance-totals">
        <div><dt>{chosen.kind === "annual" ? "Годовая сценарная экономия" : "Снижение электрического ввода"}</dt><dd>{fmt(chosen.value,chosen.kind === "annual" ? 0 : 1)} {chosen.unit}</dd></div>
        {chosen.money!=null&&<div><dt>Денежный эффект</dt><dd>{fmt(chosen.money)} тыс. ₽/год</dd></div>}
        <div><dt>CAPEX</dt><dd>{chosen.capex==null ? "Требует оценки" : `${fmt(chosen.capex)} тыс. ₽`}</dd></div>
        <div><dt>Окупаемость</dt><dd>{chosen.capex==null ? "Требует оценки" : chosen.capex === 0 ? "Без CAPEX" : chosen.payback==null ? "Не определена" : `${fmt(chosen.payback)} лет`}</dd></div>
      </dl>
      <p className="muted">{chosen.kind === "annual" ? "Сценарий сохранения выбранного режима и принятой годовой наработки. Достижимость эффекта требует проверки." : "Сценарий одного выбранного НА: его расход распределён по сети, остальные насосы выключены. Это не оценка совместной работы станции."}</p>
      {chosen.assumptions.length>0&&<details><summary>Условия оценки</summary><ul>{chosen.assumptions.map(note=><li key={note}>{note}</li>)}</ul></details>}
      <div className="content-actions">
        <LinkButton href={`#${chosen.stage === "hall" ? "machine-block" : chosen.stage === "pipes" ? "pipelines" : "wells"}`}>Разобрать потери участка</LinkButton>
        {chosen.intervention&&<Button loading={comparison.loading} onClick={()=>setIntervention(chosen.intervention)}>Оценить сценарий</Button>}
      </div>
      {intervention&&<Status {...comparison}/>}
      {result&&<section className="network-comparison" aria-label="Результат сценария мероприятия">
        <h4>{result.name}</h4><p>До: {fmt(result.before.input_kw,1)} кВт · После: {fmt(result.after.input_kw,1)} кВт · Снижение: {fmt(result.saving_kw,1)} кВт.</p>
        <details><summary>Условия сценария</summary><ul>{result.assumptions.map(note=><li key={note}>{note}</li>)}</ul></details>
      </section>}
    </section> : <>
      {id&&!loading&&!network.loading&&<p className="notice" role="status">Это мероприятие недоступно для выбранного режима или участка.</p>}
      <MeasureCards actions={rows} context={context}/>
      {!rows.length&&!loading&&!network.loading&&eligible&&<p className="muted">Для выбранного участка применимые мероприятия не рассчитаны.</p>}
    </>}
  </Panel>;
}
