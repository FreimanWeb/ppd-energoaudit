import {useId,useState} from "react";
import {Button,LinkButton} from "../../shared/ui/Button";
import {fmt} from "../../shared/ui/format";

export type OperatorBalance={
  boundary:"wellhead_after_choke";
  input_kw:number;bg_kw:number;output_kw:number;total_loss_kw:number;
  groups:{id:string;power_kw:number;children:{id:string;name:string;power_kw:number}[]}[];
};

const stages=[
  {id:"hall",label:"Машинный блок",route:"machine-block"},
  {id:"pipes",label:"Трубопроводы",route:"pipelines"},
  {id:"wells",label:"Скважины и арматура",route:"wells"},
];

function Reading({power,input}:{power?:number|null;input?:number}){
  const known=typeof power === "number" && Number.isFinite(power);
  return <>
    <strong className="loss-flow-value">{known ? `${fmt(power,1)} кВт` : "Нет оценки"}</strong>
    <span className="loss-flow-share">{known && input && input>0 ? `${fmt(power/input*100,1)} % потребления` : ""}</span>
  </>;
}

export function LossFlow({balance,activeStage,onHover,onFocus}:{
  balance?:OperatorBalance|null;activeStage:string|null;
  onHover:(id:string|null)=>void;onFocus:(id:string|null)=>void;
}){
  const [expanded,setExpanded]=useState<Record<string,boolean>>({});
  const prefix=useId();
  return <div className="loss-flow">
    <div className="loss-flow-stages">
      {stages.map(stage=>{
        const group=balance?.groups.find(group=>group.id===stage.id);
        const open=Boolean(expanded[stage.id]),id=`${prefix}-${stage.id}`;
        return <article className="loss-flow-stage" key={stage.id} data-stage={stage.id}
          data-active={activeStage===stage.id ? true : undefined} data-power={group?.power_kw}
          onPointerEnter={()=>onHover(stage.id)} onPointerLeave={()=>onHover(null)}
          onFocus={()=>onFocus(stage.id)} onBlur={()=>onFocus(null)}>
          <div className="loss-flow-parent">
            <Button variant="secondary" className="loss-flow-toggle" aria-label={`Состав потерь: ${stage.label}`}
              aria-expanded={open} aria-controls={id} onClick={()=>setExpanded(previous=>({...previous,[stage.id]:!previous[stage.id]}))}>
              <span className="loss-flow-label">{stage.label}</span>
              <svg className="loss-flow-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
              <Reading power={group?.power_kw} input={balance?.input_kw}/>
            </Button>
            <div className="loss-flow-actions"><LinkButton href={`#${stage.route}`}>Подробнее</LinkButton></div>
          </div>
          <div id={id} className="loss-flow-children" hidden={!open}>
            {group?.children.length ? <ul aria-label={`Состав: ${stage.label}`}>{group.children.map(child=><li key={child.id} data-child-power={child.power_kw}>
              <span>{child.name}</span><Reading power={child.power_kw} input={balance?.input_kw}/>
            </li>)}</ul> : <p className="muted">Недостаточно данных для разложения.</p>}
          </div>
        </article>;
      })}
    </div>
    <details className="loss-flow-balance">
      <summary>Баланс мощности</summary>
      <p>100 % — потреблённая мощность</p>
    <dl className="loss-flow-energy">
      <div><dt>Потреблённая мощность</dt><dd><Reading power={balance?.input_kw} input={balance?.input_kw}/></dd></div>
      <div><dt>Мощность на БГ <small>Промежуточный итог</small></dt><dd><Reading power={balance?.bg_kw} input={balance?.input_kw}/></dd></div>
      <div><dt>На устьях после штуцеров <small>Выходная мощность</small></dt><dd><Reading power={balance?.output_kw} input={balance?.input_kw}/></dd></div>
    </dl>
    <p className="loss-flow-boundary">Граница графа — устья после штуцеров. Трение в стволах находится за этой границей и рассматривается в подробном разборе скважин.</p>
    </details>
  </div>;
}
