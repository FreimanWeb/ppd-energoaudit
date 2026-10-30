import type { ReactNode } from "react";
import { Tooltip } from "./Tooltip";
import "../styles/pages.css";

export function Panel({
  title,
  children,
  caption,
  help,
  action,
}: {
  title: string;
  children: ReactNode;
  caption?: string;
  help?: ReactNode;
  action?: ReactNode;
}) {
  const heading = <h2>{title}{help && <Tooltip label={title} content={help} />}</h2>;
  return (
    <section className="page-panel">
      {action ? <header className="panel-heading">{heading}{action}</header> : heading}
      {caption && <p className="muted">{caption}</p>}
      {children}
    </section>
  );
}
