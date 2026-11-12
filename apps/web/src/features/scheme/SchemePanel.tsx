import {useEffect,useLayoutEffect,useRef,useState} from "react";
import {Button} from "../../shared/ui/Button";
import type { Topology } from "../../shared/types";
import { fmt } from "../../shared/ui/format";
import { Scheme } from "./Scheme";
import {type OperatorBalance,LossFlow} from "./LossFlow";
import "./schemeLosses.css";

const DETAIL_WIDTH=1400;

type SchemeNetwork={status?:string;total_loss_kw?:number|null;operator_balance?:OperatorBalance|null;warnings?:string[];network?:{well_count?:number}};

export function SchemePanel({topology,pressures,stationNetwork}: {
  topology?: Topology; stationNetwork?:SchemeNetwork;
  pressures?: Record<string,{p_in_mpa:number;p_out_mpa:number}>;
}) {
  const [hovered,setHovered]=useState<string|null>(null),[focused,setFocused]=useState<string|null>(null);
  const activeStage=hovered ?? focused;
  const [fit,setFit]=useState(true),[fullscreen,setFullscreen]=useState(false);
  const root=useRef<HTMLElement>(null),dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{if(fullscreen && !dialog.current?.open) dialog.current?.showModal();},[fullscreen]);
  const canvas=useRef<HTMLDivElement>(null);
  const [leaders,setLeaders]=useState<{id:string;stage:string;path:string}[]>([]);
  const [textScale,setTextScale]=useState(1);
  const [canEnlarge,setCanEnlarge]=useState(false);
  useLayoutEffect(()=>{
    const element=canvas.current;
    if(!element) return;
    const update=()=>{
      const bounds=element.getBoundingClientRect();
      setCanEnlarge((element.parentElement?.clientWidth ?? DETAIL_WIDTH)<DETAIL_WIDTH);
      const svg=element.querySelector<SVGSVGElement>('.equipment-scheme');
      const equipment=svg?.getBoundingClientRect();
      if(!svg || !equipment?.width) return;
      setTextScale(Math.max(1,Math.round(svg.viewBox.baseVal.width/equipment.width*100)/100));
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
    if(element.parentElement) observer.observe(element.parentElement);
    element.querySelectorAll('.equipment-scheme,.loss-flow-article').forEach(node=>observer.observe(node));
    element.addEventListener('scroll',schedule,true);
    update();
    return ()=>{observer.disconnect();cancelAnimationFrame(frame);element.removeEventListener('scroll',schedule,true);};
  },[topology,fit,fullscreen]);
  const balance=stationNetwork?.status === "scenario" ? stationNetwork.operator_balance : null;
  const wellCount = stationNetwork?.network?.well_count;
  const content=<>
    <div className="section-heading"><h2>Условная технологическая схема ППД</h2>
      {topology && <div className="scheme-view-actions">
        {canEnlarge && <>
          <Button variant="secondary" aria-pressed={fit} onClick={()=>setFit(true)}>Вписать целиком</Button>
          <Button variant="secondary" aria-pressed={!fit} onClick={()=>setFit(false)}>Крупнее</Button>
        </>}
        <Button variant="secondary" data-expand autoFocus={fullscreen} onClick={()=>fullscreen ? dialog.current?.close() : setFullscreen(true)}>{fullscreen ? "Свернуть" : "На весь экран"}</Button>
      </div>}
    </div>
    <p className="scheme-source">Вся станция: совместно работающие НА. Баланс до устьев после штуцеров; трение в стволах за границей расчёта. Скважины и водоводы показаны группами. Выберите участок или статью потерь.</p>
    {topology && <>
      {!fit && canEnlarge && <p className="scheme-scroll-hint">Крупная схема: прокручивайте по горизонтали или откройте на весь экран.</p>}
      <div className="scheme-layout" data-fit={fit} tabIndex={0} role="region" aria-label="Технологическая схема с прокруткой"><div className="scheme-canvas" ref={canvas} style={{minWidth:fit ? 0 : DETAIL_WIDTH}}>
        <Scheme textScale={textScale} balance={balance} topology={topology} aggregate="" pressures={pressures} activeStage={activeStage} onStageHover={setHovered} onStageFocus={setFocused} wellCount={typeof wellCount === "number" && wellCount > 0 ? wellCount : undefined} />
        <LossFlow balance={balance} activeStage={activeStage} onHover={setHovered} onFocus={setFocused}/>
        <svg className="scheme-leaders" aria-hidden="true">{leaders.map(line=><path key={line.id} data-loss={line.id} data-stage={line.stage} d={line.path} data-active={activeStage===line.stage?true:undefined}/>)}</svg>
      </div></div>
      <details className="scheme-method"><summary>Данные и границы расчёта</summary>
      {balance
        ? <p className="scheme-source">Потери до устьев: {fmt(balance.total_loss_kw,1)} кВт. Доли показаны от потреблённой мощности, полезная мощность не относится к потерям. Сценарная оценка: параметры внешней сети частично синтетические. Учтены совместно работающие НА станции. Трение, местные сопротивления и штуцирование объединены на участке от БГ до устьев скважин. Нормы потерь по участкам для цветовой оценки пока не заданы.</p>
        : <p className="scheme-source" role="status">Доли потерь недоступны для выбранного режима. Откройте участок для просмотра имеющихся данных.</p>}
      <p className="scheme-source">Источник схемы: {topology.source}</p></details>
    </>}
  </>;
  return <section ref={root} className="scheme-panel" aria-label="Условная технологическая схема ППД">
    {!fullscreen && content}
    <dialog ref={dialog} className="scheme-dialog" aria-label="Технологическая схема на весь экран" onClose={()=>{
      setFullscreen(false);
      requestAnimationFrame(()=>root.current?.querySelector<HTMLButtonElement>("[data-expand]")?.focus());
    }}>{fullscreen && content}</dialog>
  </section>;
}
