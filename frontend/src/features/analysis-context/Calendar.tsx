import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useResource } from "../../shared/api";
import { monthDays } from "../../app/navigation.mjs";
import "./calendar.css";

const names: Record<string, string> = {
  ready: "Пригодные сутки",
  snapshot: "Режимный снимок",
  unfit: "Непригодные данные",
  insufficient: "Недостаточно данных",
  loading: "Загружается статус",
  unknown: "Статус не определён",
};
const shiftMonth = (month: string, offset: number) => {
  const [year, number] = month.split("-").map(Number);
  return new Date(Date.UTC(year, number - 1 + offset, 1)).toISOString().slice(0, 7);
};

export function Calendar({ path, day, dates, onChange }: {
  path: string; day: string; dates: string[]; onChange: (day: string) => void;
}) {
  const [open, setOpen] = useState(false), [chosenMonth, setMonth] = useState("");
  const [position, setPosition] = useState({ left: 8, top: 8 });
  const trigger = useRef<HTMLButtonElement>(null), popup = useRef<HTMLDivElement>(null);
  const monthInput = useRef<HTMLInputElement>(null);
  const firstMonth = dates[0]?.slice(0, 7) ?? "", lastMonth = dates.at(-1)?.slice(0, 7) ?? "";
  const clampMonth = (value: string) => value < firstMonth ? firstMonth : value > lastMonth ? lastMonth : value;
  const month = clampMonth(chosenMonth || day.slice(0, 7) || lastMonth);
  const statuses = useResource<{ statuses: Record<string, string> }>(
    open && month ? `${path}/calendar?month=${month}` : null,
  );
  function close() {
    setOpen(false);
    trigger.current?.focus();
  }
  useLayoutEffect(() => {
    if (!open) return;
    const reposition = () => {
      const anchor = trigger.current?.getBoundingClientRect(), box = popup.current?.getBoundingClientRect();
      if (!anchor || !box) return;
      const left = Math.max(8, Math.min(anchor.left, window.innerWidth - box.width - 8));
      const below = anchor.bottom + 6;
      const top = Math.max(8, Math.min(below + box.height <= window.innerHeight - 8 ? below : anchor.top - box.height - 6, window.innerHeight - box.height - 8));
      setPosition(previous => previous.left === left && previous.top === top ? previous : { left, top });
    };
    reposition();
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [open, month, statuses.loading]);
  useEffect(() => {
    if (!open) return;
    monthInput.current?.focus();
    const outside = (event: PointerEvent) => {
      if (!popup.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) close();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        close();
      }
    };
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", escape, true);
    return () => {
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("keydown", escape, true);
    };
  }, [open]);
  return <div className="date-picker">
    <span className="date-label">Дата</span>
    <button ref={trigger} type="button" className="date-trigger" aria-label="Дата"
      aria-haspopup="dialog" aria-expanded={open} data-date={day} disabled={!dates.length}
      onClick={() => { if (open) close(); else { setMonth(""); setOpen(true); } }}>
      <span>{day ? day.split("-").reverse().join(".") : "Нет дат"}</span>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 11h18M7 15h2m3 0h2m3 0h1"/></svg>
    </button>
    {open && createPortal(<div ref={popup} role="dialog" aria-label="Выбор даты" className="date-popover" style={position}>
      <div className="date-month-controls">
        <button type="button" aria-label="Предыдущий месяц" disabled={month <= firstMonth} onClick={() => setMonth(shiftMonth(month, -1))}>‹</button>
        <input ref={monthInput} aria-label="Месяц календаря" type="month" value={month} min={firstMonth} max={lastMonth} onChange={event => setMonth(event.target.value)} />
        <button type="button" aria-label="Следующий месяц" disabled={month >= lastMonth} onClick={() => setMonth(shiftMonth(month, 1))}>›</button>
      </div>
      {statuses.error && <p className="date-status-error" role="alert">{statuses.error}</p>}
      <div className="date-grid" aria-busy={statuses.loading}>
        {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map(name => <span key={name} className="date-weekday">{name}</span>)}
        {monthDays(month).map((date: string | null, index: number) => {
          if (!date) return <span key={`blank-${index}`} />;
          const available = dates.includes(date);
          const status = available ? statuses.loading ? "loading" : statuses.data?.statuses[date] || "unknown" : "empty";
          const title = available ? names[status] || names.unknown : "Нет телеметрии";
          return <button key={date} type="button" disabled={!available} className={`date-cell ${status}`}
            aria-label={`${date}: ${title}`} aria-pressed={date === day} title={title}
            onClick={() => { onChange(date); close(); }}>{Number(date.slice(8))}</button>;
        })}
      </div>
      <div className="date-legend">{["ready", "snapshot", "unfit", "insufficient"].map(status => <span key={status}><i className={status}/>{names[status]}</span>)}</div>
      <span className="date-help">Цвет показывает пригодность данных для расчёта.</span>
    </div>, document.body)}
  </div>;
}
