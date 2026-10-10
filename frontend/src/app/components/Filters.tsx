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
  return (
    <details className="object-filter">
      <summary>
        {title}
        <span>{chosen.length || "Все"}</span>
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
