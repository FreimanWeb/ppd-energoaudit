import {lossLabel,lossLabels} from "../../shared/lossLabels";
import {LinkButton} from '../../shared/ui/Button';
import {fmt} from '../../shared/ui/format';

export type OperatorBalance={
  boundary:'wellhead_after_choke';
  input_kw:number;bg_kw:number;output_kw:number;total_loss_kw:number;
  groups:{id:string;power_kw:number;children:{id:string;name:string;power_kw:number}[]}[];
};

const stages=[
  {id:'hall',label:'Машинный блок и обвязка до БГ',route:'machine-losses'},
  {id:'pipes',label:'От БГ до устьев скважин',route:'pipelines'},
];
const articles=[
  {id:'nominal',stage:'hall'},
  {id:'efficiency',stage:'hall'},
  {id:'pump_bg',stage:'hall'},
  {id:'friction',stage:'pipes'},
  {id:'local',stage:'pipes'},
  {id:'choke',stage:'pipes'},
];

export function LossFlow({balance,activeStage,onHover,onFocus}:{
  balance?:OperatorBalance|null;activeStage:string|null;
  onHover:(id:string|null)=>void;onFocus:(id:string|null)=>void;
}){
  return <div className="loss-flow" aria-label="Статьи потерь">
    <div className="loss-flow-articles">
      {articles.map(article=>{
        const stage=stages.find(stage=>stage.id === article.stage)!;
        const child=balance?.groups.flatMap(group=>group.children).find(child=>child.id === article.id);
        const power=child?.power_kw;
        const label=lossLabel(child?.name ?? (lossLabels as Record<string,string>)[article.id]);
        const known=typeof power === 'number' && Number.isFinite(power);
        return <LinkButton key={article.id} href={`#${stage.route}`} className="loss-flow-article"
          data-loss={article.id} data-stage={stage.id} data-power={known ? power : undefined} data-active={activeStage === stage.id ? true : undefined}
          onPointerEnter={()=>onHover(stage.id)} onPointerLeave={()=>onHover(null)} onFocus={()=>onFocus(stage.id)} onBlur={()=>onFocus(null)}>
          <span className="loss-flow-article-label">{label}</span>
          <strong className="loss-flow-value">{known ? `${fmt(power,1)} кВт` : 'Нет оценки'}</strong>
          <span className="loss-flow-share">{known && balance && balance.input_kw>0 ? `${fmt(power/balance.input_kw*100,1)} % потребления` : ''}</span>
        </LinkButton>;
      })}
    </div>
    <div className="loss-flow-groups">{stages.map(stage=><div className="loss-flow-group" key={stage.id} data-stage={stage.id}><span>{stage.label}</span></div>)}</div>
  </div>;
}
