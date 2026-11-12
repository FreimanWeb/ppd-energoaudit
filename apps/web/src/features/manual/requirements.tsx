import type { Requirement } from "../../shared/types";
import { LinkButton } from "../../shared/ui/Button";
import { fmt } from "../../shared/ui/format";
import "./manual.css";

const statusText: Record<Requirement["status"], string> = {
  missing: "Нет данных",
  pending_confirmation: "Требует подтверждения",
  conflict: "Конфликт данных",
  assumed: "Принято допущение",
  ready: "Данные есть",
};

function valueText(value: unknown): string {
  if (typeof value === "number") return fmt(value);
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  if (Array.isArray(value)) return `Точек: ${value.length}`;
  if (value && typeof value === "object") {
    if ("reference" in value && typeof value.reference === "string")
      return value.reference || "Источник не указан";
    return JSON.stringify(value);
  }
  return String(value);
}

/** Целевая страница действия по требованию: журнал оборудования, сеть или
 *  страница готовности. Параметр focus подсвечивает нужный параметр. */
export function requirementHref(req: Requirement): string {
  const url = new URL(location.href);
  url.searchParams.delete("edit");
  url.searchParams.delete("focus");
  if (req.action === "equipment") {
    url.searchParams.set("focus", req.key);
    url.hash = "equipment-journal";
  } else if (req.action === "network") {
    url.hash = "network";
  } else {
    url.hash = "onboarding";
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

function RequirementCards({ items }: { items: Requirement[] }) {
  return items.length > 0 ? <ul className="requirement-list">
    {items.map(req => <li key={req.key} className={`requirement req-${req.status}`}>
      <div className="requirement-head">
        <span className={`req-badge req-${req.status}`}>{statusText[req.status]}</span>
        <strong>{req.label}</strong>
        {req.value != null && <span className="requirement-value">{valueText(req.value)}{req.unit ? ` ${req.unit}` : ""}</span>}
      </div>
      {req.reason && <p className="requirement-reason">{req.reason}</p>}
      {req.affects.length > 0 && <p className="requirement-affects muted">Влияет на: {req.affects.join(", ")}</p>}
      {req.action === "review" ? <p className="muted">{req.action_label}</p>
        : <LinkButton href={requirementHref(req)}>{req.action_label}</LinkButton>}
    </li>)}
  </ul> : null;
}

function RequirementSummary({ items }: { items: Requirement[] }) {
  const groups = new Map<string, Requirement[]>();
  for (const req of items) {
    const key = `${req.status}:${req.reason}`;
    const group = groups.get(key);
    if (group) group.push(req);
    else groups.set(key, [req]);
  }
  return <details className="requirement-summary">
    <summary>Уточнения и допущения ({items.length})</summary>
    {[...groups].map(([key, group]) => <section key={key} className="requirement-group">
      <h4>{statusText[group[0].status]}</h4>
      {group[0].reason && <p className="muted">{group[0].reason}</p>}
      <ul className="requirement-compact-list">
        {group.map(req => <li key={req.key} className={`requirement-compact-item${req.action === "review" ? " requirement-review-item" : ""}`}>
          <div>
            <div className="requirement-head"><strong>{req.label}</strong>
              {req.value != null && <span className="requirement-value">{valueText(req.value)}{req.unit ? ` ${req.unit}` : ""}</span>}
            </div>
            {req.affects.length > 0 && <p className="requirement-affects muted">Влияет на: {req.affects.join(", ")}</p>}
          </div>
          {req.action === "review" ? <span className="muted">{req.action_label}</span>
            : <LinkButton href={requirementHref(req)} aria-label={`${req.action_label}: ${req.label}`}>Уточнить</LinkButton>}
        </li>)}
      </ul>
    </section>)}
  </details>;
}

export function RequirementList({ items, caption, compact = false }: { items: Requirement[]; caption?: string; compact?: boolean }) {
  const open = items.filter(item => item.status !== "ready");
  const done = items.filter(item => item.status === "ready");
  const refinements = compact ? open.filter(item => item.status === "pending_confirmation" || item.status === "assumed") : [];
  const visible = compact ? open.filter(item => item.status !== "pending_confirmation" && item.status !== "assumed") : open;
  return <>
    {caption && <p className="muted">{caption}</p>}
    {!items.length && <p className="muted">Требования к данным для этого разбора не сформированы.</p>}
    <RequirementCards items={visible}/>
    {refinements.length > 0 && <RequirementSummary items={refinements}/>}
    {done.length > 0 && <details className="requirement-ready"><summary>Данные, доступные для расчёта ({done.length})</summary>
      <ul>{done.map(req => <li key={req.key}>{req.label}{req.value != null ? `: ${valueText(req.value)}${req.unit ? ` ${req.unit}` : ""}` : ""}<p className="muted">{req.reason}</p></li>)}</ul>
    </details>}
  </>;
}
