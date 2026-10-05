import { useEffect,useState } from 'react';
import 'katex/dist/katex.min.css';
import { Panel,fmt,type PageProps } from './common';
import { renderEquation } from './mathRenderer.mjs';

type Entry={name?:string;latex?:string|null;subst_latex?:string|null;formula?:string;expr?:string;subst?:string;value?:unknown};
function MathEquation({latex}:{latex:string}){
 const [rendered,setRendered]=useState<{source:string;html?:string;failed?:boolean}>();
 useEffect(()=>{
  let active=true;
  renderEquation(latex).then(html=>{
   if(active)setRendered({source:latex,html});
  }).catch(()=>{if(active)setRendered({source:latex,failed:true});});
  return ()=>{active=false;};
 },[latex]);
 return rendered?.source===latex&&rendered.html?<div className="formula-expression" style={{overflowX:'auto'}} dangerouslySetInnerHTML={{__html:rendered.html}}/>:rendered?.source===latex&&rendered.failed?<p className="notice error" role="alert">Не удалось оформить формулу: {latex}</p>:<p className="formula-expression" role="status">Подготавливаем формулу…</p>;
}
export function FormulasPage(p:PageProps){
 const rows=Object.entries(p.audit?.audit.trace??{}).sort(([a],[b])=>parseInt(a)-parseInt(b));
 return <Panel title="Как получено каждое число — формулы методики" caption="Формула → подстановка величин выбранного режима → результат. Расчёт выполняется общей моделью.">{rows.length?rows.map(([id,raw])=>{const entry=raw as Entry;return <article className="formula-card" key={id}><header><strong>({id}) {entry.name??'Расчётная формула'}</strong><strong>{fmt(entry.value,4)}</strong></header>{entry.latex?<MathEquation latex={entry.latex}/>:<p className="formula-expression">{entry.formula??entry.expr}</p>}{entry.subst_latex?<MathEquation latex={entry.subst_latex}/>:<p className="formula-substitution">Подстановка: {entry.subst} → {fmt(entry.value,4)}</p>}</article>;}):<p className="notice">Для выбранного режима расчётные формулы недоступны. Выберите пригодный снимок или режим обследования.</p>}</Panel>;
}
