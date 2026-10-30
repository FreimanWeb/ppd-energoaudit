import {LinkButton} from '../../shared/ui/Button';
import {fmt} from '../../shared/ui/format';
import {catalogMeasures,measureHref} from './measureCatalog.mjs';
import {stageDefinitions} from './networkStages.mjs';
import './networkLosses.css';

export function MeasureCards({actions,context}:{actions:ReturnType<typeof catalogMeasures>;context?:Parameters<typeof measureHref>[2]}) {
  const groups=[
    {kind:'annual',title:'Годовая экономия электроэнергии',note:'Мероприятия упорядочены по кВт·ч/год при принятой наработке; стоимость и достижимость требуют отдельной оценки.'},
    {kind:'network',title:'Снижение электрической мощности',note:'Мероприятия упорядочены по кВт одного НА при прежней закачке. Эффект включает настройку напора; годовая экономия не рассчитана.'},
  ];
  return <div className="measure-groups">{groups.map(group=>{
    const rows=actions.filter(action=>action.kind===group.kind);
    return rows.length>0 && <section className="measure-group" aria-label={group.title} key={group.kind}>
      <h3>{group.title}</h3><p className="muted">{group.note}</p>
      <div className="network-measures action-list">{rows.map(action=><article className="network-measure" data-action-id={action.id} data-stage={action.stage} key={`${action.aggregate}:${action.id}`}>
        <small className="muted">{action.aggregate || context?.aggregateId} · {action.stage === 'hall' ? 'Машинный блок' : stageDefinitions.find(stage=>stage.id===action.stage)?.label}</small>
        <h4>{action.name}</h4>
        <p className="network-measure-saving">{fmt(action.value,action.kind === 'annual' ? 0 : 1)} {action.unit}</p>
        <LinkButton href={measureHref(action.id,action.stage,context ? {...context,aggregateId:action.aggregate || context.aggregateId,networkScenario:action.kind === "network" ? context.networkScenario : undefined} : null)} aria-label={`Подробнее: ${action.name}`}>Подробнее</LinkButton>
      </article>)}</div>
    </section>;
  })}</div>;
}
