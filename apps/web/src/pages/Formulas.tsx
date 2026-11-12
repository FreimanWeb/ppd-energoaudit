import { inspectionFor, inspectionHref, hallReportHref } from "../features/inspection/inspection.mjs";
import { InspectionLinks } from "../features/inspection/InspectionLinks";
import { useEffect, useState } from "react";
import { Panel } from "../shared/ui/Panel";
import { Button, LinkButton } from "../shared/ui/Button";
import { fmt } from "../shared/ui/format";
import type { PageProps } from "../shared/ui/context";
import type { Audit } from "../shared/types";
import { MathEquation } from "./MathEquation";
import { LossDetailPanel, lossDetailKey, causalHallKeys } from "../features/losses/LossDetailPanel";
import { AnnualSummary } from "../features/overview/AnnualSummary";

type Entry = { name?: string; latex?: string | null; subst_latex?: string | null; formula?: string; expr?: string; subst?: string; value?: unknown };
const groups = [
  { title: "Напор", ids: ["8", "29"] },
  { title: "Мощность", ids: ["11"] },
  { title: "КПД и загрузка", ids: ["13", "14", "24", "25-26", "27", "30"] },
  { title: "Удельный расход энергии", ids: ["16", "17"] },
  { title: "Годовые потери", ids: ["44", "45"] },
  { title: "Другие расчёты", ids: [] },
];

export function FormulasPage(p: PageProps & {audit: Audit}) {
  const annual = p.inspectionKey === "annual_losses";
  const related = inspectionFor(p.inspectionKey)?.formulas ?? [];
  const rows = Object.entries(p.audit?.audit.trace ?? {}).filter(([id]) => !annual || related.includes(id)).sort(([a], [b]) => parseInt(a) - parseInt(b));
  const [opened, setOpened] = useState<Record<string, boolean>>(() => Object.fromEntries(related.map(id => [id, true])));
  useEffect(() => { setOpened(previous => ({ ...previous, ...Object.fromEntries((inspectionFor(p.inspectionKey)?.formulas ?? []).map(id => [id, true])) })); }, [p.inspectionKey]);
  const allOpen = rows.length > 0 && rows.every(([id]) => opened[id]);
  const focus = lossDetailKey(p.inspectionKey);
  const item = inspectionFor(focus);
  const hallLoss = focus && focus === p.inspectionKey && (focus === "hall" || (item && (item.stage ?? "hall") === "hall"));
  if (hallLoss) {
    const causal = Boolean(causalHallKeys[focus] || (focus === "hydraulic_bg_loss" && new URL(location.href).searchParams.get("decomposition") === "causal"));
    const stage = causal ? "hall_causal" : "hall";
    const back = focus === "hall" || focus === "hall_causal" ? undefined : focus === "efficiency_causes" ? "efficiency_loss" : focus;
    return <Panel title="Расчёт и источники потерь" action={<LinkButton href={inspectionHref("losses", back)}>К карте потерь</LinkButton>}>
      <nav className="content-actions" aria-label="Разложение потерь">
        <LinkButton href={hallReportHref()} variant={causal ? "secondary" : "primary"} aria-current={!causal ? "page" : undefined}>По оборудованию</LinkButton>
        <LinkButton href={hallReportHref("hall_causal", "causal")} variant={causal ? "primary" : "secondary"} aria-current={causal ? "page" : undefined}>По причинам</LinkButton>
      </nav>
      {causal && <nav className="content-actions" aria-label="Уровень причинного разбора">
        <LinkButton href={hallReportHref("hall_causal", "causal")} aria-current={focus === "hall_causal" ? "page" : undefined}>Общий баланс</LinkButton>
        <LinkButton href={hallReportHref("efficiency_causes", "causal")} aria-current={focus === "efficiency_causes" ? "page" : undefined}>Составляющие отклонения КПД</LinkButton>
      </nav>}
      <LossDetailPanel key={`${stage}:${focus}`} context={p} focus={focus} stageHref={hallReportHref(stage, causal ? "causal" : "equipment")}/>
    </Panel>;
  }
  return <>
    {annual && <nav className="content-actions"><LinkButton href={inspectionHref("machine-block", undefined)}>К показателям</LinkButton></nav>}
    {annual && <AnnualSummary audit={p.audit}/>}
    <Panel title={annual ? "Формулы годовой оценки" : "Как получено каждое число — формулы методики"} help="Формула → подстановка величин выбранного режима → результат. Расчёт выполняется общей моделью.">
    <InspectionLinks metric={p.inspectionKey} />
    {p.inspectionKey && inspectionFor(p.inspectionKey) && !rows.some(([id]) => related.includes(id)) && <p className="notice">Для этого показателя формула не сохранена в расчётной трассировке. Проверьте источники и паспортные данные.</p>}
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
        return <article className="formula-card" data-highlighted={related.includes(id) || undefined} key={id}>
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
  </Panel></>;
}
