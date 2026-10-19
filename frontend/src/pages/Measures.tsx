import {Button,LinkButton} from "../shared/ui/Button";
import {useResource,segment} from "../shared/api";
import {inspectionFor,relatedMeasures,inspectionHref} from "../features/inspection/inspection.mjs";
import {InspectionLinks} from "../features/inspection/InspectionLinks";
import {contextBody,type PageProps} from "../shared/ui/context";
import {ChainMeasures} from "../features/losses/ChainMeasures";
import {MeasureEconomics,type Measures} from "../features/losses/MeasureEconomics";

export function MeasuresPage(p:PageProps) {
  const eligible=Boolean(p.objectId && p.aggregateId && (p.source==="field_trip" || p.day && p.timestamp) && p.audit?.quality.status!=="unfit");
  const resource=useResource<Measures>(eligible ? `/objects/${segment(p.objectId)}/aggregates/${segment(p.aggregateId)}/measures` : null,contextBody(p,{basis:"annual"}));
  const data=resource.data;
  const focus=inspectionFor(p.inspectionKey);
  const annual=focus ? relatedMeasures(data?.annual ?? [],p.inspectionKey) : data?.annual ?? [];
  return <section aria-label={focus ? "Связанные мероприятия" : undefined}>
    {focus && <div className="inspection-result">
      <InspectionLinks metric={p.inspectionKey}/>
      <h3>Мероприятия по выбранной причине потерь</h3>
      <div className="content-actions">
        <LinkButton href={inspectionHref("losses",p.inspectionKey)}>Вернуться к составляющей потерь</LinkButton>
        <Button variant="secondary" onClick={()=>{const url=new URL(location.href);url.searchParams.delete("inspect");history.pushState(null,"",url);window.dispatchEvent(new PopStateEvent("popstate"));}}>Показать все мероприятия</Button>
      </div>
    </div>}
    <ChainMeasures key={`${p.objectId}:${p.aggregateId}:${p.source}:${p.day}:${p.timestamp}`} context={p} annual={annual} eligible={eligible} loading={resource.loading} error={resource.error}
      annualDetail={id=>data ? <MeasureEconomics key={id} context={p} measureId={id} baseline={data}/> : null}/>
  </section>;
}
