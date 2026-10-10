import type { ReactNode } from "react";
import { Tooltip } from "./Tooltip";
import "../styles/pages.css";

export function Panel({
  title,
  children,
  caption,
  help,
}: {
  title: string;
  children: ReactNode;
  caption?: string;
  help?: ReactNode;
}) {
  return (
    <section className="page-panel">
      <h2>{title}{help && <Tooltip label={title} content={help} />}</h2>
      {caption && <p className="muted">{caption}</p>}
      {children}
    </section>
  );
}
