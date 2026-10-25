import {useEffect,useMemo,useRef,useState} from 'react';
import {Button} from '../../shared/ui/Button';
import {fmt} from '../../shared/ui/format';
import {PIPELINE_NODE_WIDTH,pipelineTopology} from './pipelineTopology.mjs';
import './pipelineSchematic.css';

export type SchematicPipeline={name:string;start:string;end:string;length_m:number;sizes:string;q_m3h:number;velocity_ms:number;dp_friction_mpa:number};
export type SchematicWell={well:string;q_m3h:number;path_complete:boolean;path_pipeline_names:string[];p_after_choke_mpa:number|null;loss_kw:number;flags:string[]};
export type SchematicNode={id:string;kind:'source'|'unknown'|'pipe'|'well';label:string;x:number;y:number;pipe?:SchematicPipeline;well?:SchematicWell};

const short=(value:string)=>value.length>21 ? value.slice(0,20)+'…' : value;

export default function PipelineSchematic({pipelines,wells}:{pipelines:SchematicPipeline[];wells:SchematicWell[]}){
  const graph=useMemo(()=>pipelineTopology(pipelines,wells),[pipelines,wells]);
  const [selected,setSelected]=useState<string|null>(null);
  const scroll=useRef<HTMLDivElement>(null);
  const root=useRef<HTMLElement>(null);
  const dialog=useRef<HTMLDialogElement>(null);
  const [fullscreen,setFullscreen]=useState(false);
  useEffect(()=>{if(fullscreen && !dialog.current?.open) dialog.current?.showModal();},[fullscreen]);
  const node=graph.nodes.find(item=>item.id===selected);
  const selectedWell=node?.well;
  const highlighted=new Set(selectedWell ? [
    selected!,...selectedWell.path_pipeline_names.map(name=>`pipe:${name}`),
    selectedWell.path_complete ? 'station' : 'unknown',
  ] : selected ? [selected] : []);
  const byId=new Map(graph.nodes.map(item=>[item.id,item]));
  const choose=(id:string)=>{
    setSelected(id);
    requestAnimationFrame(()=>scroll.current?.querySelector('[aria-pressed="true"]')?.scrollIntoView({block:'center',inline:'center'}));
  };
  const content=<>
    <div className="pipeline-schematic-heading"><div><h3>Схема водоводов</h3>
      <p className="muted">Связи восстановлены по реестру. Расположение условное, без масштаба; места врезок и трассы на местности не заданы.</p></div>
      <div className="pipeline-schematic-actions"><label>Найти скважину<select aria-label="Найти скважину" value={selectedWell?.well ?? ''} onChange={event=>{if(event.target.value) choose(`well:${event.target.value}`); else {setSelected(null);scroll.current?.scrollTo(0,0);}}}>
        <option value="">Все маршруты</option>
        {[...wells].sort((a,b)=>a.well.localeCompare(b.well,'ru',{numeric:true})).map(well=><option key={well.well} value={well.well}>Скв {well.well}</option>)}
      </select></label>
      <Button variant="secondary" data-expand autoFocus={fullscreen} onClick={()=>fullscreen ? dialog.current?.close() : setFullscreen(true)}>{fullscreen ? 'Свернуть' : 'На весь экран'}</Button></div>
    </div>
    <p className="pipeline-schematic-legend"><span>КНС / БГ → водоводы → скважины</span><span>Пунктир — связь со станцией не подтверждена</span></p>
    {graph.nodes.length ? <div ref={scroll} className="pipeline-schematic-scroll" tabIndex={0} role="region" aria-label="Схема с прокруткой">
      <svg width={graph.width} height={graph.height} role="group" aria-label="Связность водоводов и скважин">
        {graph.edges.map(edge=>{
          const a=byId.get(edge.source)!,b=byId.get(edge.target)!;
          const x=a.x+PIPELINE_NODE_WIDTH,y=a.y+29,bx=b.x,by=b.y+29,mid=(x+bx)/2;
          return <path key={JSON.stringify([edge.source,edge.target])} className="pipeline-schematic-edge" data-uncertain={edge.uncertain} data-highlighted={highlighted.has(edge.source)&&highlighted.has(edge.target)} d={`M ${x} ${y} C ${mid} ${y}, ${mid} ${by}, ${bx} ${by}`} />;
        })}
        {graph.nodes.map(item=><g key={item.id} transform={`translate(${item.x},${item.y})`} data-kind={item.kind} className="pipeline-schematic-node" role="button" tabIndex={0}
          aria-label={item.kind==='pipe' ? `Водовод: ${item.id.slice(5)}` : item.label} aria-pressed={selected===item.id}
          data-highlighted={highlighted.has(item.id)} onClick={()=>choose(item.id)}
          onFocus={event=>event.currentTarget.scrollIntoView({block:'nearest',inline:'nearest'})}
          onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();choose(item.id);}}}>
          <title>{item.kind==='pipe' ? item.id.slice(5) : item.label}</title>
          <rect width={PIPELINE_NODE_WIDTH} height={58} rx={item.kind==='well' ? 25 : 8}/>
          <text x={12} y={23}>{short(item.label)}</text>
          <text className="pipeline-schematic-node-meta" x={12} y={43}>{short(item.pipe ? `${fmt(item.pipe.length_m,0)} м · ${item.pipe.sizes}` : item.well ? `${fmt(item.well.q_m3h)} м³/ч` : item.kind==='source' ? 'Источник сети' : 'Неполный маршрут')}</text>
        </g>)}
      </svg>
    </div> : <p className="notice">Нет данных для схемы водоводов.</p>}
    <p className="muted pipeline-schematic-help">Схему можно прокручивать. Выберите водовод или скважину; скважину можно найти в списке. Её маршрут будет выделен. Tab и Enter работают на элементах схемы.</p>
    {node && <section className="pipeline-schematic-detail" aria-label="Параметры выбранного элемента" aria-live="polite">
      <div className="pipeline-schematic-detail-heading"><h4>{node.kind==='pipe' ? `Водовод: ${node.id.slice(5)}` : node.label}</h4>
      <Button variant="secondary" aria-label="Закрыть параметры" onClick={()=>setSelected(null)}>Закрыть</Button></div>
      {node.pipe && <><p>{node.pipe.start} → {node.pipe.end}</p><dl>
        <div><dt>Длина</dt><dd>{fmt(node.pipe.length_m,0)} м</dd></div><div><dt>Трубы D×s</dt><dd>{node.pipe.sizes}</dd></div>
        <div><dt>Расход</dt><dd>{fmt(node.pipe.q_m3h)} м³/ч</dd></div><div><dt>Трение</dt><dd>{fmt(node.pipe.dp_friction_mpa,3)} МПа</dd></div>
      </dl></>}
      {node.kind==='pipe' && !node.pipe && <p className="notice">Водовод есть в маршруте, но расчётных параметров для него нет.</p>}
      {selectedWell && <><dl><div><dt>Расход</dt><dd>{fmt(selectedWell.q_m3h)} м³/ч</dd></div><div><dt>Давление после штуцера</dt><dd>{fmt(selectedWell.p_after_choke_mpa)} МПа</dd></div><div><dt>Потери до устья</dt><dd>{fmt(selectedWell.loss_kw)} кВт</dd></div></dl>
        {!selectedWell.path_complete && <p className="notice">Связь со станцией не подтверждена. Показана только известная часть маршрута.</p>}
        {selectedWell.path_pipeline_names.length>0 && <ol aria-label="Маршрут скважины">{selectedWell.path_pipeline_names.map(name=><li key={name}>{name}</li>)}</ol>}
        {selectedWell.flags.length>0 && <p className="muted">{selectedWell.flags.join('; ')}</p>}
      </>}
      {node.kind==='source' && <p>Начало полного маршрута по именованным узлам станции в реестре.</p>}
      {node.kind==='unknown' && <p className="notice">Неполные маршруты сгруппированы здесь для просмотра. Общий физический узел для них не установлен.</p>}
    </section>}
  </>;
  return <section ref={root} className="pipeline-schematic" aria-label="Схема водоводов">
    {!fullscreen && content}
    <dialog ref={dialog} className="pipeline-schematic-dialog" aria-label="Схема водоводов на весь экран" onClose={()=>{
      setFullscreen(false);
      requestAnimationFrame(()=>root.current?.querySelector<HTMLButtonElement>('[data-expand]')?.focus());
    }}>{fullscreen && content}</dialog>
  </section>;
}
