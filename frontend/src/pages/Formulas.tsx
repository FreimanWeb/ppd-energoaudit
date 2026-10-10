import 'katex/dist/katex.min.css';
import { useState } from "react";
import { Panel } from "../shared/ui/Panel";
import { Button } from "../shared/ui/Button";
import { fmt } from "../shared/ui/format";
import type { PageProps } from "../shared/ui/context";
import { MathEquation } from "./MathEquation";

type Entry = { name?: string; latex?: string | null; subst_latex?: string | null; formula?: string; expr?: string; subst?: string; value?: unknown };
const groups = [
  { title: "Напор", ids: ["8", "29"] },
  { title: "Мощность", ids: ["11"] },
  { title: "КПД и загрузка", ids: ["13", "14", "24", "25-26", "27", "30"] },
  { title: "Удельный расход энергии", ids: ["16", "17"] },
  { title: "Годовые потери", ids: ["44", "45"] },
  { title: "Другие расчёты", ids: [] },
];

export function FormulasPage(p: PageProps) {
  const rows = Object.entries(p.audit?.audit.trace ?? {}).sort(([a], [b]) => parseInt(a) - parseInt(b));
  const [opened, setOpened] = useState<Record<string, boolean>>({});
  const allOpen = rows.length > 0 && rows.every(([id]) => opened[id]);
  return <Panel title="Как получено каждое число — формулы методики" help="Формула → подстановка величин выбранного режима → результат. Расчёт выполняется общей моделью.">
    {rows.length ? <>
      <Button variant="secondary" onClick={() => setOpened(Object.fromEntries(rows.map(([id]) => [id, !allOpen])))}>
        {allOpen ? "Свернуть все" : "Раскрыть все"}
      </Button>
      {groups.map(group => {
        const entries = rows.filter(([id]) => group.ids.length
          ? group.ids.includes(id)
          : !groups.some(known => known.ids.includes(id)));
        return entries.length > 0 && <section key={group.title} aria-label={group.title}>
          <h3>{group.title}</h3>
          {entries.map(([id, raw]) => {
        const entry = raw as Entry;
        return <article className="formula-card" key={id}>
          <header><strong>({id}) {entry.name ?? 'Расчётная формула'}</strong><strong>{fmt(entry.value, 4)}</strong></header>
          <details open={!!opened[id]} onToggle={(event) => {
            const open = event.currentTarget.open;
            setOpened(previous => !!previous[id] === open ? previous : { ...previous, [id]: open });
          }}>
            <summary>Формула и подстановка</summary>
            {entry.latex ? <MathEquation latex={entry.latex} /> : <p className="formula-expression">{entry.formula ?? entry.expr}</p>}
            {entry.subst_latex ? <MathEquation latex={entry.subst_latex} /> : <p className="formula-substitution">Подстановка: {entry.subst} → {fmt(entry.value, 4)}</p>}
          </details>
        </article>;
          })}
        </section>;
      })}
    </> : <p className="notice">Для выбранного режима расчётные формулы недоступны. Выберите пригодный снимок или режим обследования.</p>}
  </Panel>;
}
