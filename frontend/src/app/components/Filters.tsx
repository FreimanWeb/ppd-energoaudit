import { useEffect, useRef } from "react";

export function Filters({
  title,
  options,
  chosen,
  onChange,
}: {
  title: string;
  options: string[];
  chosen: string[];
  onChange: (value: string[]) => void;
}) {
  const root = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const outside = (event: MouseEvent) => {
      if (root.current?.open && !root.current.contains(event.target as Node)) root.current.open = false;
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || !root.current?.open) return;
      event.preventDefault();
      event.stopPropagation();
      root.current.open = false;
      root.current.querySelector("summary")?.focus();
    };
    document.addEventListener("click", outside);
    document.addEventListener("keydown", escape, true);
    return () => {
      document.removeEventListener("click", outside);
      document.removeEventListener("keydown", escape, true);
    };
  }, []);
  const selection = chosen.length === 1 ? chosen[0] : chosen.length ? `Выбрано: ${chosen.length}` : "Все";
  return (
    <details ref={root} className="object-filter" data-active={chosen.length > 0}>
      <summary aria-label={`Фильтр ${title}: ${selection}`}>
        <span className="object-filter-title">{title}</span>
        <span className="object-filter-value" title={chosen.join(", ") || "Все"}>{selection}</span>
        <svg className="object-filter-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
      </summary>
      <div>
        {options.map((value) => (
          <label key={value}>
            <input
              type="checkbox"
              aria-label={`${title}: ${value}`}
              checked={chosen.includes(value)}
              onChange={(e) =>
                onChange(
                  e.target.checked
                    ? [...chosen, value]
                    : chosen.filter((x) => x !== value),
                )
              }
            />
            {value}
          </label>
        ))}
      </div>
    </details>
  );
}
