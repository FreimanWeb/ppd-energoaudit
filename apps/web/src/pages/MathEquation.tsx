import "katex/dist/katex.min.css";
import { useEffect, useState } from "react";
import { useHorizontalOverflow } from "../shared/ui/useHorizontalOverflow";
import { renderEquation } from "./mathRenderer.mjs";

export function MathEquation({ latex }: { latex: string }) {
  const [rendered, setRendered] = useState<{ source: string; html?: string; failed?: boolean }>();
  const { container, scrollable } = useHorizontalOverflow(rendered?.html);
  useEffect(() => {
    let active = true;
    renderEquation(latex).then(html => { if (active) setRendered({ source: latex, html }); })
      .catch(() => { if (active) setRendered({ source: latex, failed: true }); });
    return () => { active = false; };
  }, [latex]);
  if (rendered?.source === latex && rendered.html) return <div>
    <div ref={container} className="formula-expression" style={{ overflowX: "auto" }}
      tabIndex={scrollable ? 0 : undefined} role={scrollable ? "region" : undefined}
      aria-label={scrollable ? "Формула с горизонтальной прокруткой" : undefined}
      dangerouslySetInnerHTML={{ __html: rendered.html }} />
    {scrollable && <p className="table-scroll-hint">Прокрутите формулу вправо, чтобы увидеть её целиком.</p>}
  </div>;
  return rendered?.source === latex && rendered.failed
    ? <p className="notice error" role="alert">Не удалось оформить формулу: {latex}</p>
    : <p className="formula-expression" role="status">Подготавливаем формулу…</p>;
}
