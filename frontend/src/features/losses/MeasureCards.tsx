import {LinkButton} from '../../shared/ui/Button';
import {fmt} from '../../shared/ui/format';
import {catalogMeasures,measureHref} from './measureCatalog.mjs';
import {stageDefinitions} from './networkStages.mjs';
import './networkLosses.css';

export function MeasureCards({actions,context}:{actions:ReturnType<typeof catalogMeasures>;context?:Parameters<typeof measureHref>[2]}) {
  return <div className="network-measures action-list">{actions.map(action=><article className="network-measure" data-action-id={action.id} data-stage={action.stage} key={`${action.aggregate}:${action.id}`}>
    <small className="muted">{action.aggregate || context?.aggregateId} · {action.stage === 'hall' ? 'Машинный блок' : stageDefinitions.find(stage=>stage.id===action.stage)?.label}</small>
    <h4>{action.name}</h4>
    <p className="network-measure-saving">{fmt(action.value,action.kind === 'annual' ? 0 : 1)} {action.unit}</p>
    <p className="muted">{action.kind === 'annual' ? 'Годовая сценарная оценка' : 'Сценарий одного НА при прежней закачке; с настройкой напора'}</p>
    <LinkButton href={measureHref(action.id,action.stage,context ? {...context,aggregateId:action.aggregate || context.aggregateId,networkScenario:action.kind === "network" ? context.networkScenario : undefined} : null)} aria-label={`Подробнее: ${action.name}`}>Подробнее</LinkButton>
  </article>)}</div>;
}
