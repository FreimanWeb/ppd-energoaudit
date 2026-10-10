import 'katex/dist/katex.min.css';
import { Panel } from "../shared/ui/Panel";
import { fmt } from "../shared/ui/format";
import type { PageProps } from "../shared/ui/context";
import { MathEquation } from "./MathEquation";

type Entry={name?:string;latex?:string|null;subst_latex?:string|null;formula?:string;expr?:string;subst?:string;value?:unknown};
export function FormulasPage(p:PageProps){
 const rows=Object.entries(p.audit?.audit.trace??{}).sort(([a],[b])=>parseInt(a)-parseInt(b));
 return <Panel title="Как получено каждое число — формулы методики" help="Формула → подстановка величин выбранного режима → результат. Расчёт выполняется общей моделью.">{rows.length?rows.map(([id,raw])=>{const entry=raw as Entry;return <article className="formula-card" key={id}><header><strong>({id}) {entry.name??'Расчётная формула'}</strong><strong>{fmt(entry.value,4)}</strong></header>{entry.latex?<MathEquation latex={entry.latex}/>:<p className="formula-expression">{entry.formula??entry.expr}</p>}{entry.subst_latex?<MathEquation latex={entry.subst_latex}/>:<p className="formula-substitution">Подстановка: {entry.subst} → {fmt(entry.value,4)}</p>}</article>;}):<p className="notice">Для выбранного режима расчётные формулы недоступны. Выберите пригодный снимок или режим обследования.</p>}</Panel>;
}
