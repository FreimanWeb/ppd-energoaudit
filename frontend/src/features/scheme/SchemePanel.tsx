import {useLayoutEffect,useRef,useState,type ReactNode} from "react";
import type { Audit, Topology } from "../../shared/types";
import { fmt } from "../../shared/ui/format";
import { Scheme } from "./Scheme";
import { segment, useResource } from "../../shared/api";
import {type OperatorBalance,LossFlow} from "./LossFlow";
import "./schemeLosses.css";

type SchemeNetwork={status?:string;total_loss_kw?:number|null;operator_balance?:OperatorBalance|null;warnings?:string[];network?:{well_count?:number}};

export function SchemePanel({topology,audit,aggregate="",pressures,status,station=false,stationNetwork}: {
  topology?: Topology; audit?: Audit; aggregate?: string;
  station?:boolean;stationNetwork?:SchemeNetwork;
  pressures?: Record<string,{p_in_mpa:number;p_out_mpa:number}>; status?: ReactNode;
}) {
  const [hovered,setHovered]=useState<string|null>(null),[focused,setFocused]=useState<string|null>(null);
  const activeStage=hovered ?? focused;
  const canvas=useRef<HTMLDivElement>(null);
  const [leaders,setLeaders]=useState<{id:string;path:string}[]>([]);
  useLayoutEffect(()=>{
    const element=canvas.current;
    if(!element) return;
    const update=()=>{
      const bounds=element.getBoundingClientRect();
      const row=element.querySelector<HTMLElement>(".loss-flow-stages");
      if(!row) return;
      const rowBounds=row.getBoundingClientRect();
      const anchors=["hall","pipes","wells"].flatMap(id=>{
        const area=element.querySelector(`.scheme-area-link[data-stage="${id}"] rect`);
        const stage=element.querySelector<HTMLElement>(`.loss-flow-stage[data-stage="${id}"]`);
        if(!area || !stage) return [];
        const from=area.getBoundingClientRect();
        return [{id,stage,x:from.x+from.width/2,y:from.bottom}];
      });
      anchors.forEach((anchor,index)=>{
        const spacing=Math.min(rowBounds.width,index>0 ? anchor.x-anchors[index-1].x : Infinity,index<anchors.length-1 ? anchors[index+1].x-anchor.x : Infinity);
        anchor.stage.style.left=`${anchor.x-rowBounds.x}px`;
        anchor.stage.style.width=`${Math.max(260,spacing-24)}px`;
      });
      row.style.height=`${Math.max(0,...anchors.map(anchor=>anchor.stage.getBoundingClientRect().height))}px`;
      const paths=anchors.map(anchor=>{
        const card=anchor.stage.querySelector(".loss-flow-parent")!.getBoundingClientRect();
        return {id:anchor.id,path:`M ${anchor.x-bounds.x} ${anchor.y-bounds.y} V ${card.top-bounds.y}`};
      });
      setLeaders(previous=>JSON.stringify(previous)===JSON.stringify(paths)?previous:paths);
    };
    let frame=0;
    const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(update);};
    const observer=new ResizeObserver(schedule);
    observer.observe(element);
    element.querySelectorAll('.equipment-scheme,.loss-flow-stage').forEach(node=>observer.observe(node));
    element.addEventListener('scroll',schedule,true);
    update();
    return ()=>{observer.disconnect();cancelAnimationFrame(frame);element.removeEventListener('scroll',schedule,true);};
  },[topology]);
  const timestamp = audit?.snapshot?.timestamp;
  const supported = ["kns54an","demo-ppd"].includes(audit?.audit.object_id ?? "");
  const network = useResource<SchemeNetwork>(
    !station && supported && audit && audit.quality.status !== "unfit" && (audit?.source === "field_trip" || timestamp)
      ? `/objects/${segment(audit?.audit.object_id)}/aggregates/${segment(aggregate)}/network-losses` : null,
    JSON.stringify({source:audit?.source,...(audit?.source === "telemetry" && timestamp ? {day:timestamp.slice(0,10),timestamp} : {})}),
  );
  const map = station ? stationNetwork : network.data;
  const balance=map?.status === "scenario" ? map.operator_balance : null;
  const wellCount = map?.network?.well_count;
  return <section className="scheme-panel" aria-label="Условная технологическая схема ППД">
    <div className="section-heading"><h2>Условная технологическая схема ППД</h2></div>
    <p className="scheme-source">Скважины и водоводы показаны условно группами. Нажмите на узел графа ниже, чтобы раскрыть состав потерь.</p>
    {status}
    {topology && <>
      <div className="scheme-layout"><div className="scheme-canvas" ref={canvas}>
        <Scheme topology={topology} aggregate={aggregate} audit={station?undefined:audit} pressures={pressures} activeStage={activeStage} onStageHover={setHovered} onStageFocus={setFocused} wellCount={typeof wellCount === "number" && wellCount > 0 ? wellCount : undefined} />
        <svg className="scheme-leaders" aria-hidden="true">{leaders.map(line=><path key={line.id} data-stage={line.id} d={line.path} data-active={activeStage===line.id?true:undefined}/>)}</svg>
        <LossFlow balance={balance} activeStage={activeStage} onHover={setHovered} onFocus={setFocused}/>
      </div></div>
      <details className="scheme-method"><summary>Данные и границы расчёта</summary>
      {balance
        ? <p className="scheme-source">Потери до устьев: {fmt(balance.total_loss_kw,1)} кВт. Доли показаны от потреблённой мощности, полезная мощность не относится к потерям. Сценарная оценка: параметры внешней сети частично синтетические. {station ? "Учтены совместно работающие НА станции." : "Сценарий выбранного НА; остальные насосы в сценарии выключены."} Местные сопротивления сети и арматуры включены в трубопроводы. Нормы потерь по участкам для цветовой оценки пока не заданы.</p>
        : <p className="scheme-source" role="status">{network.loading ? "Рассчитываем доли потерь…" : network.error ? `Распределение потерь недоступно: ${network.error}` : "Доли потерь недоступны для выбранного режима. Откройте участок для просмотра имеющихся данных."}</p>}
      <p className="scheme-source">Источник схемы: {topology.source}</p></details>
    </>}
  </section>;
}
