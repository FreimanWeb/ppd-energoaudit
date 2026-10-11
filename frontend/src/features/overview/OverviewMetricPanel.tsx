import { useEffect, useId, useState, type ReactNode } from "react";
import { Button } from "../../shared/ui/Button";
import { Panel } from "../../shared/ui/Panel";

export function OverviewMetricPanel({ title, actionLabel, layout, children, details }: {
  title: string;
  actionLabel: string;
  layout: "ure" | "efficiency";
  children: ReactNode;
  details: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [animating, setAnimating] = useState(false);
  const toggle = () => {
    setAnimating(!window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    setOpen(value => !value);
  };
  const detailsId = useId();
  useEffect(() => {
    if (!animating) return;
    // Повторный клик может отменить transition без transitionend.
    const timer = window.setTimeout(() => setAnimating(false), 260);
    return () => window.clearTimeout(timer);
  }, [open, animating]);

  return (
    <Panel title={title} action={<Button variant="secondary" className="reference-toggle" aria-expanded={open} aria-controls={detailsId} onClick={toggle}>{actionLabel}<svg className="overview-disclosure-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg></Button>}>
      <div className={`overview-metric-values overview-metric-values-${layout}${open ? " is-open" : ""}${animating ? " is-animating" : ""}`} onTransitionEnd={event => {
        if (event.target === event.currentTarget && ["grid-template-columns", "grid-template-rows"].includes(event.propertyName)) setAnimating(false);
      }}>
        <div className="overview-metric-main">{children}</div>
        <div id={detailsId} className="overview-metric-details" aria-hidden={!open} inert={!open}>
          {details}
        </div>
      </div>
    </Panel>
  );
}
