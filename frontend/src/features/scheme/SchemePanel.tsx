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
  const [leaders,setLeaders]=useState<{id:string;stage:string;path:string}[]>([]);
  useLayoutEffect(()=>{
    const element=canvas.current;
    if(!element) return;
    const update=()=>{
      const bounds=element.getBoundingClientRect();
      const equipment=element.querySelector('.equipment-scheme')?.getBoundingClientRect();
      if(!equipment) return;
      const paths=[...element.querySelectorAll<SVGCircleElement>('.scheme-loss-anchor')].flatMap(anchor=>{
        const id=anchor.dataset.loss!;
        const card=element.querySelector(`.loss-flow-article[data-loss="${id}"]`);
        if(!card) return [];
        const from=card.getBoundingClientRect(),to=anchor.getBoundingClientRect();
        const x1=from.x+from.width/2-bounds.x,y1=from.top-bounds.y;
        const x2=to.x+to.width/2-bounds.x,y2=to.y+to.height/2-bounds.y;
        return [{id,stage:anchor.dataset.stage!,path:`M ${x1} ${y1} L ${x2} ${equipment.bottom-bounds.y+12} V ${y2}`}];
      });
      setLeaders(previous=>JSON.stringify(previous)===JSON.stringify(paths)?previous:paths);
    };
    let frame=0;
    const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(update);};
    const observer=new ResizeObserver(schedule);
    observer.observe(element);
    element.querySelectorAll('.equipment-scheme,.loss-flow-article').forEach(node=>observer.observe(node));
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
    <p className="scheme-source">Скважины и водоводы показаны условно группами. Выберите статью потерь, чтобы открыть подробности участка.</p>
    {status}
    {topology && <>
      <div className="scheme-layout"><div className="scheme-canvas" ref={canvas}>
        <Scheme balance={balance} topology={topology} aggregate={aggregate} audit={station?undefined:audit} pressures={pressures} activeStage={activeStage} onStageHover={setHovered} onStageFocus={setFocused} wellCount={typeof wellCount === "number" && wellCount > 0 ? wellCount : undefined} />
        <LossFlow balance={balance} activeStage={activeStage} onHover={setHovered} onFocus={setFocused}/>
        <svg className="scheme-leaders" aria-hidden="true">{leaders.map(line=><path key={line.id} data-loss={line.id} data-stage={line.stage} d={line.path} data-active={activeStage===line.stage?true:undefined}/>)}</svg>
      </div></div>
      <details className="scheme-method"><summary>Данные и границы расчёта</summary>
      {balance
        ? <p className="scheme-source">Потери до устьев: {fmt(balance.total_loss_kw,1)} кВт. Доли показаны от потреблённой мощности, полезная мощность не относится к потерям. Сценарная оценка: параметры внешней сети частично синтетические. {station ? "Учтены совместно работающие НА станции." : "Сценарий выбранного НА; остальные насосы в сценарии выключены."} Трение, местные сопротивления и штуцирование объединены на участке от БГ до устьев скважин. Нормы потерь по участкам для цветовой оценки пока не заданы.</p>
        : <p className="scheme-source" role="status">{network.loading ? "Рассчитываем доли потерь…" : network.error ? `Распределение потерь недоступно: ${network.error}` : "Доли потерь недоступны для выбранного режима. Откройте участок для просмотра имеющихся данных."}</p>}
      <p className="scheme-source">Источник схемы: {topology.source}</p></details>
    </>}
  </section>;
}
