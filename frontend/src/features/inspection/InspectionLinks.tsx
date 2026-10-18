import { LinkButton } from "../../shared/ui/Button";
import { inspectionFor, inspectionHref } from './inspection.mjs';
import './inspection.css';

export function InspectionLinks({ metric }: { metric?: string }) {
  const item = metric ? inspectionFor(metric) : undefined;
  if (!item) return null;
  const page = location.hash.slice(1);
  return <div className="inspection-context" role="region" aria-label="Разбор показателя">
    <strong>{item.title}</strong>
    <nav aria-label="Основание показателя">
      {[["sources", "Источники показателя"], ["formulas", "Формулы показателя"]].map(([target, label]) => page === target
        ? <span key={target} aria-current="page">{label}</span>
        : <LinkButton key={target} href={inspectionHref(target, metric)}>{label}</LinkButton>)}
    </nav>
  </div>;
}
