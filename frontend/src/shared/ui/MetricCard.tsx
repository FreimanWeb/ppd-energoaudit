import { Fragment } from "react";
import { formatMetric } from "../format/number.mjs";
import { Tooltip } from "./Tooltip";
import "./metrics.css";

export type MetricSegment = {
  label: string;
  value: unknown;
  unit: string;
  help: string;
  tone?: string;
  reason?: string;
  digits?: number;
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
  digits?: number;
};

export function MetricCard({
  label, value, unit, help, tone = "neutral", caption, reason, segments, digits,
}: Metric) {
  return (
    <div
      className={`kpi metric-card metric-${tone}${segments ? " metric-values" : ""}`}
      data-tone={tone}
    >
      {label && (
        <div className="metric-label">
          <span>{label}</span>
          <Tooltip label={label} content={`${help}${reason ? ` ${reason}` : ""}`} />
        </div>
      )}
      {segments ? (
        <div className="metric-values-row">
          {segments.map((item, index) => (
            <Fragment key={item.label}>
              {index > 0 && <span className="metric-segment-divider" aria-hidden="true" />}
              <div className="metric-segment" data-tone={item.tone ?? "neutral"}>
                {item.label && <span className="metric-segment-label">{item.label}</span>}
                <Tooltip
                  label={label ? `${label}: ${item.label}` : item.label}
                  content={item.reason ? `${item.help} ${item.reason}` : item.help}
                >
                  <strong className={item.value == null ? "metric-empty" : undefined}>{item.value == null ? "Нет данных" : formatMetric(item.value, item.unit, item.digits)}</strong>
                </Tooltip>
                <small className="metric-unit">{item.unit}</small>
              </div>
            </Fragment>
          ))}
        </div>
      ) : (
        <>
          <Tooltip label={`Оценка ${label}`} content={[caption, reason].filter(Boolean).join(". ")}>
            <strong className={value == null ? "metric-empty" : undefined}>{value == null ? "Нет данных" : formatMetric(value, unit, digits)}</strong>
          </Tooltip>
          <small className="metric-unit">{unit || "о.е."}</small>
        </>
      )}
    </div>
  );
}
