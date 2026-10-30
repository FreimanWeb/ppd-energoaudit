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
