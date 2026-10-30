import type { ReactNode } from "react";
import { Tooltip } from "./Tooltip";
import { fmt } from "./format";
import { useHorizontalOverflow } from "./useHorizontalOverflow";

export type TableColumn = { key: string; label: string; help?: ReactNode; align?: "start" | "end"; digits?: number; render?: (row: Record<string, unknown>) => ReactNode };

export function Table({
  rows,
  columns,
  rowHighlighted,
}: {
  rows: Record<string, unknown>[];
  columns: TableColumn[];
  rowHighlighted?: (row: Record<string, unknown>) => boolean;
}) {
  const { container, scrollable } = useHorizontalOverflow(rows);
  const numeric = (column: TableColumn) => column.align === "end" || (column.align !== "start" && rows.some(row => typeof row[column.key] === "number"));
  return rows.length ? (
    <div className="table-region">
    <div ref={container} className="table-scroll" tabIndex={scrollable ? 0 : undefined} role={scrollable ? "region" : undefined} aria-label={scrollable ? "Таблица с горизонтальной прокруткой" : undefined}>
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={numeric(c) ? "numeric-cell" : "text-cell"}>{c.label}{c.help && <Tooltip label={c.label} content={c.help} />}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} data-highlighted={rowHighlighted?.(r) || undefined}>
              {columns.map((c) => (
                <td key={c.key} className={numeric(c) ? "numeric-cell" : "text-cell"}>{c.render ? c.render(r) : fmt(r[c.key], c.digits)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    {scrollable && <p className="table-scroll-hint">Прокрутите таблицу вправо, чтобы увидеть остальные столбцы.</p>}
    </div>
  ) : (
    <p className="notice">Нет строк для отображения.</p>
  );
}
