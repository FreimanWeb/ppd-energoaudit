import { useState } from "react";
import { useResource } from "./api";
import { monthDays } from "./navigation.mjs";

const names: Record<string, string> = {
  ready: "Пригодные сутки",
  snapshot: "Режимный снимок",
  unfit: "Непригодные данные",
  insufficient: "Недостаточно данных",
};
export function Calendar({
  path,
  day,
  dates,
  onChange,
}: {
  path: string;
  day: string;
  dates: string[];
  onChange: (day: string) => void;
}) {
  const [chosenMonth, setMonth] = useState("");
  const month =
    chosenMonth || day.slice(0, 7) || dates.at(-1)?.slice(0, 7) || "";
  const statuses = useResource<{ statuses: Record<string, string> }>(
    month ? `${path}/calendar?month=${month}` : null,
  );
  if (!month || !dates.length) return null;
  return (
    <details className="calendar-panel">
      <summary>Календарь пригодности данных</summary>
      <label>
        Месяц
        <input
          aria-label="Месяц календаря"
          type="month"
          value={month}
          min={dates[0].slice(0, 7)}
          max={dates.at(-1)?.slice(0, 7)}
          onChange={(e) => setMonth(e.target.value)}
        />
      </label>
      {statuses.error && <p className="notice error">{statuses.error}</p>}
      <div className="calendar-grid">
        {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((x) => (
          <span className="weekday" key={x}>
            {x}
          </span>
        ))}
        {monthDays(month).map((date: string | null, index: number) =>
          date ? (
            <button
              key={date}
              disabled={!dates.includes(date)}
              className={`calendar-day ${statuses.data?.statuses[date] || "unknown"} ${date === day ? "selected" : ""}`}
              aria-label={`${date}: ${names[statuses.data?.statuses[date] || ""] || "Нет телеметрии"}`}
              aria-pressed={date === day}
              title={
                names[statuses.data?.statuses[date] || ""] || "Нет телеметрии"
              }
              onClick={() => onChange(date)}
            >
              {Number(date.slice(8))}
            </button>
          ) : (
            <span key={`blank-${index}`} />
          ),
        )}
      </div>
      <p className="calendar-legend">
        Зелёный — пригодны · жёлтый — снимок · красный — непригодны · серый —
        недостаточно данных
      </p>
    </details>
  );
}
