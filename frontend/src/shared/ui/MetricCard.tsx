import { followInternalLink } from "./navigation";
import { Fragment, type ReactNode } from "react";
import { formatMetric } from "../format/number.mjs";
import { Tooltip } from "./Tooltip";
import "./metrics.css";
type Link = { label: string; href: string };
function MetricActions({ links, label }: { links?: Link[]; label: string }) {
  return links?.length ? <details className="metric-actions" onKeyDown={event => {
    if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); }
  }}><summary aria-label={`Разобрать: ${label}`}>⋯</summary><nav aria-label={`Действия: ${label}`}>{links.map(link => <a onClick={followInternalLink} href={link.href} key={link.label}>{link.label}</a>)}</nav></details> : null;
}

export type MetricSegment = {
  valueSuffix?: ReactNode;
  label: string;
  value: unknown;
  unit: string;
  help: string;
  tone?: string;
  reason?: string;
  digits?: number;
  links?: Link[];
};

export type Metric = {
  label: string;
  value: unknown;
  unit: string;
  help: string;
  tone?: string;
  caption?: string;
  reason?: string;
  segments?: MetricSegment[];
  helpOnValue?: boolean;
  digits?: number;
  links?: Link[];
};

function explanation(...texts: (string | undefined)[]) {
  return texts.filter(Boolean).flatMap(text => text!.split(/\n\s*\n/)).map((paragraph, index) => <p key={index}>{paragraph}</p>);
}

export function MetricCard({
  label, value, unit, help, tone = "neutral", caption, reason, segments, digits, links, helpOnValue = false,
}: Metric) {
  return (
    <div
      className={`kpi metric-card metric-${tone}${segments ? " metric-values" : ""}`}
      data-tone={tone}
    >
      {label && (
        <div className="metric-label">
          <span>{label}</span>
          <MetricActions links={links} label={label} />
          {!helpOnValue && <Tooltip label={label} content={explanation(help, reason)} />}
        </div>
      )}
      {segments ? (
        <div className="metric-values-row">
          {segments.map((item, index) => (
            <Fragment key={item.label}>
              {index > 0 && <span className="metric-segment-divider" aria-hidden="true" />}
              <div className="metric-segment" data-tone={item.tone ?? "neutral"}>
                {item.label && <div className="metric-segment-heading"><span className="metric-segment-label">{item.label}</span><MetricActions links={item.links} label={label ? `${label}: ${item.label}` : item.label} /></div>}
                <Tooltip
                  label={label ? `${label}: ${item.label}` : item.label}
                  content={explanation(item.help, item.reason)}
                >
                  <span className={item.valueSuffix ? "metric-reading metric-reading-annotated" : "metric-reading"}>
                    <strong className={item.value == null ? "metric-empty" : undefined}>{item.value == null ? "Нет данных" : formatMetric(item.value, item.unit, item.digits)}</strong>{item.valueSuffix}
                  </span>
                </Tooltip>
                <small className="metric-unit">{item.unit}</small>
              </div>
            </Fragment>
          ))}
        </div>
      ) : (
        <>
          <Tooltip label={helpOnValue ? label : `Оценка ${label}`} content={explanation(helpOnValue ? help : undefined, caption, reason)}>
            <strong className={value == null ? "metric-empty" : undefined}>{value == null ? "Нет данных" : formatMetric(value, unit, digits)}</strong>
          </Tooltip>
          <small className="metric-unit">{unit || "о.е."}</small>
        </>
      )}
    </div>
  );
}
