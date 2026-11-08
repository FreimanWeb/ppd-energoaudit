import { segment, useResource } from "../../shared/api";
import { LinkButton } from "../../shared/ui/Button";
import { Status } from "../../shared/ui/Status";
import { fmt } from "../../shared/ui/format";
import { inspections, inspectionFor, inspectionHref, relatedMeasures } from "../inspection/inspection.mjs";
import { lossInspection } from "./lossDetail.mjs";
import "../inspection/inspection.css";

type Context = { objectId: string; aggregateId: string; source: "telemetry" | "field_trip"; timestamp?: string | null };
type Annual = { measure_id: string; name: string; addresses?: string; money_saving_krub: number; cls: string };

/** Источники, формулы и мероприятия статьи — как в разборе составляющей на карте потерь. */
export function LossProposals({ lossKey, context }: { lossKey: string; context: Context }) {
  const metric = lossInspection(lossKey, inspections);
  const addresses = inspectionFor(metric)?.addresses ?? [];
  const ready = addresses.length > 0 && (context.source === "field_trip" || context.timestamp);
  const proposals = useResource<{ annual: Annual[] }>(
    ready ? `/objects/${segment(context.objectId)}/aggregates/${segment(context.aggregateId)}/measures` : null,
    JSON.stringify({ source: context.source, basis: "annual", ...(context.source === "telemetry" && context.timestamp ? { day: context.timestamp.slice(0, 10), timestamp: context.timestamp } : {}) }),
  );
  if (!metric) return null;
  const measures = relatedMeasures(proposals.data?.annual ?? [], metric);
  return <section className="loss-measures" aria-label="Предлагаемые мероприятия">
    <header><h3>Что можно изменить</h3>
      <nav aria-label="Основание составляющей">
        <LinkButton href={inspectionHref("sources", metric)}>Источники</LinkButton>
        <LinkButton href={inspectionHref("formulas", metric)}>Формулы</LinkButton>
        {measures.length > 0 && <LinkButton href={inspectionHref("measures", metric)}>Оценить мероприятия</LinkButton>}
      </nav>
    </header>
    <Status {...proposals} empty="Нет данных для оценки мероприятий." />
    {measures.length > 0 ? <ul>{measures.map(measure => <li key={measure.measure_id}>
      <div><span>{measure.name}</span><small>{measure.cls === "сценарная оценка" ? "Сценарий · CAPEX требует оценки" : measure.cls}</small></div>
      <div className="loss-measure-effect"><strong>{fmt(measure.money_saving_krub, 1)} тыс. ₽/год</strong><small>Расчётный эффект</small></div>
    </li>)}</ul> : !proposals.loading && !proposals.error && proposals.data && <p className="muted">Для этой составляющей мероприятия пока не предложены.</p>}
  </section>;
}
