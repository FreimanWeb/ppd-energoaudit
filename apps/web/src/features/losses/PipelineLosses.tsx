import {lossLabels} from "../../shared/lossLabels";
import {Table} from '../../shared/ui/Table';
import {fmt} from '../../shared/ui/format';
import {WellLinks} from '../../shared/wellSelection';
import {useHorizontalOverflow} from '../../shared/ui/useHorizontalOverflow';
import {pipelineLosses} from './pipelineLossData.mjs';

export type PipelineSegment={
  id:string;pipeline_id:string;name:string;length_m:number;inner_diameter_mm:number;
  flow_m3h:number;pressure_loss_mpa:number;power_kw:number;source_sheet:string;source_row:number;
};
export type PipelineWell={
  id:string;flow_m3h:number;armature_loss_kw:number;choke_loss_kw:number|null;
  required_pressure_mpa:number;available_pressure_mpa:number;deficit_mpa:number;
  path_pipeline_ids?:string[];synthetic_connection?:boolean;
};

export function PipelineLosses({segments,wells}:{segments:PipelineSegment[];wells:PipelineWell[]}){
  const {pipelines,unassignedWells}=pipelineLosses(segments,wells);
  const {container,scrollable}=useHorizontalOverflow(pipelines);
  return <section className="pipeline-losses" aria-label="Потери по трубопроводам">
    <h3>Трубопроводы</h3>
    <p className="stage-basis">Трение учтено в каждом трубопроводе один раз. Местные сопротивления и штуцирование отнесены к конечной ветви перед скважиной. Итого — до устьев, без трения в НКТ. Расчёт по выбранному НА; расходы и часть параметров сценарные.</p>
    {pipelines.length>0 && <>
      <div ref={container} className="pipeline-loss-scroll" tabIndex={scrollable ? 0 : undefined} role={scrollable ? 'region' : undefined} aria-label={scrollable ? 'Трубопроводы с горизонтальной прокруткой' : undefined}>
        <div className="pipeline-loss-list">
          <div className="pipeline-loss-header" aria-hidden="true"><span>Трубопровод</span><span>{lossLabels.friction}, кВт</span><span>{lossLabels.local}, кВт</span><span>{lossLabels.choke}, кВт</span><span>Итого, кВт</span><span/></div>
          {pipelines.map(pipeline=><details className="pipeline-loss-row" key={pipeline.id} data-pipeline={pipeline.id}>
            <summary>
              <span><strong>{pipeline.name}</strong><small>{pipeline.id} · {fmt(pipeline.length_m,0)} м · {pipeline.wells.length} скв.{pipeline.shared ? ' · общий участок' : ''}</small></span>
              <strong aria-label={`${lossLabels.friction}: ${fmt(pipeline.friction_kw)} кВт`}>{fmt(pipeline.friction_kw)}</strong>
              <strong aria-label={`${lossLabels.local}: ${fmt(pipeline.local_kw)} кВт`}>{fmt(pipeline.local_kw)}</strong>
              <strong aria-label={`${lossLabels.choke}: ${fmt(pipeline.choke_kw)} кВт`}>{fmt(pipeline.choke_kw)}</strong>
              <strong aria-label={`Итого: ${fmt(pipeline.total_kw)} кВт`}>{fmt(pipeline.total_kw)}</strong>
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
            </summary>
            <div className="pipeline-loss-detail">
              <p className="stage-basis">Расход: {fmt(pipeline.flow_m3h)} м³/ч. {pipeline.shared ? 'Общий участок питает несколько скважин: его трение не повторяется в итогах ответвлений.' : 'В строке учтены собственные участки трубопровода.'}</p>
              {pipeline.choke_kw === null && <p className="notice" role="status">Недостаточно напора у подключённой напрямую скважины. Штуцирование и общий итог не определены.</p>}
              <h4>Собственные участки</h4>
              <Table rows={pipeline.sections.map(section=>({...section,source:`${section.source_sheet}, строка ${section.source_row}`}))} columns={[
                {key:'id',label:'Участок'},{key:'length_m',label:'Длина, м'},{key:'inner_diameter_mm',label:'Диаметр, мм'},
                {key:'flow_m3h',label:'Расход, м³/ч'},{key:'pressure_loss_mpa',label:'Потери давления, МПа',digits:3},
                {key:'power_kw',label:`${lossLabels.friction}, кВт`},{key:'source',label:'Источник'},
              ]}/>
              <h4>Подключённые скважины</h4>
              <p className="stage-basis">Видны все скважины ниже по потоку. Потери скважин через ответвления показаны справочно: они включены в итог соответствующей конечной ветви.</p>
              <Table rows={pipeline.wells.map(well=>({...well,connection:`${well.path_pipeline_ids?.at(-1) === pipeline.id ? 'Напрямую' : 'Через ответвление'}${well.synthetic_connection ? ' · синтетическая связь' : ''}`,path:well.path_pipeline_ids?.join(' → ')}))} rowHighlighted={row=>Number(row.deficit_mpa)>0} columns={[
                {key:'id',label:'Скважина'},{key:'inspect',label:'Подробнее',render:row=><WellLinks code={String(row.id)}/>},{key:'connection',label:'Подключение'},{key:'path',label:'Маршрут от БГ'},
                {key:'flow_m3h',label:'Расход, м³/ч'},{key:'armature_loss_kw',label:`${lossLabels.local}, кВт`},
                {key:'choke_loss_kw',label:`${lossLabels.choke}, кВт`},{key:'deficit_mpa',label:'Дефицит, МПа',digits:3},
              ]}/>
            </div>
          </details>)}
        </div>
      </div>
      {scrollable && <p className="table-scroll-hint">Прокрутите список вправо, чтобы увидеть все составляющие.</p>}
    </>}
    {unassignedWells.length>0 && <section aria-label="Скважины без привязки">
      <h4>Скважины без привязки к трубопроводу</h4>
      <p className="notice">Маршрут не определён. Их местные сопротивления и штуцирование не распределены по трубопроводам.</p>
      <Table rows={unassignedWells} columns={[{key:'id',label:'Скважина'},{key:'inspect',label:'Подробнее',render:row=><WellLinks code={String(row.id)}/>},{key:'flow_m3h',label:'Расход, м³/ч'},{key:'armature_loss_kw',label:`${lossLabels.local}, кВт`},{key:'choke_loss_kw',label:`${lossLabels.choke}, кВт`}]}/>
    </section>}
  </section>;
}
