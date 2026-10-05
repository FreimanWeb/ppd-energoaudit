import type { ReactNode } from "react";
import "../pages.css";
export type PageProps = {
  objectId: string;
  aggregateId: string;
  day: string;
  timestamp: string;
  source: "telemetry" | "field_trip";
  audit?: {
    audit: { trace: Record<string, unknown> };
    quality: { status: string };
  };
};
export const fmt = (value: unknown, digits = 2) =>
  value === null || value === undefined
    ? "—"
    : typeof value === "number"
      ? new Intl.NumberFormat("ru-RU", {
          maximumFractionDigits: digits,
        }).format(value)
      : String(value);
export const dateShift = (day: string, delta: number) => {
  if (!day) return "";
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + delta);
  return date.toISOString().slice(0, 10);
};
export function Status({
  loading,
  error,
  data,
  empty = "Нет данных для выбранного периода.",
}: {
  loading?: boolean;
  error?: string;
  data?: unknown;
  empty?: string;
}) {
  return error ? (
    <p className="notice error" role="alert">
      {error}
    </p>
  ) : loading ? (
    <p className="notice" role="status">
      Загружаем данные…
    </p>
  ) : data === undefined ? (
    <p className="notice">{empty}</p>
  ) : null;
}
export function Panel({
  title,
  children,
  caption,
}: {
  title: string;
  children: ReactNode;
  caption?: string;
}) {
  return (
    <section className="page-panel">
      <h2>{title}</h2>
      {caption && <p className="muted">{caption}</p>}
      {children}
    </section>
  );
}
export function Table({
  rows,
  columns,
}: {
  rows: Record<string, unknown>[];
  columns: { key: string; label: string }[];
}) {
  return rows.length ? (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key}>{fmt(r[c.key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="notice">Нет строк для отображения.</p>
  );
}
export const contextBody = (
  p: PageProps,
  extra: Record<string, unknown> = {},
) =>
  JSON.stringify({
    source: p.source,
    ...(p.source === "telemetry" ? { day: p.day, timestamp: p.timestamp } : {}),
    ...extra,
  });
export function Range({
  start,
  end,
  onStart,
  onEnd,
}: {
  start: string;
  end: string;
  onStart: (v: string) => void;
  onEnd: (v: string) => void;
}) {
  return (
    <>
      <label>
        Начало периода
        <input
          aria-label="Начало периода"
          type="date"
          value={start}
          max={end || undefined}
          onChange={(e) => onStart(e.target.value)}
        />
      </label>
      <label>
        Конец периода
        <input
          aria-label="Конец периода"
          type="date"
          value={end}
          min={start || undefined}
          onChange={(e) => onEnd(e.target.value)}
        />
      </label>
    </>
  );
}
