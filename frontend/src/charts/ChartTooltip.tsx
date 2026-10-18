import { useLayoutEffect, useRef, type CSSProperties } from "react";
export type ChartTooltipRow = { name?: string; value: number | [number, number]; unit?: string; share?: number; color?: string };
const numberFormat = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });
const number = (value: number) => numberFormat.format(value);
export function ChartTooltip({ title, rows, style }: { title: string; rows: ChartTooltipRow[]; style?: CSSProperties }) {
  const element = useRef<HTMLDivElement>(null);
  useLayoutEffect(()=>{
    if (!element.current || typeof style?.left !== "number" || typeof style?.top !== "number") return;
    const bounds = element.current.getBoundingClientRect();
    const left = Math.max(12,Math.min(bounds.left,window.innerWidth-bounds.width-12));
    const top = Math.max(12,Math.min(bounds.top,window.innerHeight-bounds.height-12));
    element.current.style.left = `${style.left + left - bounds.left}px`;
    element.current.style.top = `${style.top + top - bounds.top}px`;
  },[style?.left,style?.top,title,rows]);
  const compact = rows.length === 1 && (!rows[0].name || rows[0].name === title);
  return <div ref={element} className={`native-chart-tooltip visx-tooltip${compact ? " chart-tooltip-compact" : ""}`} role="status" aria-live="polite" style={style}>
    {title && <strong>{title}</strong>}
    {rows.map((row, i) => <div key={i}>
      <p>{!compact && <><span className="native-chart-tooltip-swatch" style={{ background: row.color }} /><span>{row.name}</span></>}
        <b>{Array.isArray(row.value) ? row.value.map(number).join(" — ") : number(row.value)}{row.unit ? ` ${row.unit}` : ""}</b>
      </p>
      {row.share != null && Number.isFinite(row.share) && <p className="chart-tooltip-share">{number(row.share * 100)} %</p>}
    </div>)}
    {!rows.length && <p>Нет измерений</p>}
  </div>;
}
