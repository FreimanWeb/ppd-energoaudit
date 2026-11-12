import { Plot, type Trace } from "../../charts/Plot";
import { useState, type ReactNode } from "react";
import { segment, useResource } from "../../shared/api";
import { Button } from "../../shared/ui/Button";
import { Panel } from "../../shared/ui/Panel";
import { Status } from "../../shared/ui/Status";
import { Table } from "../../shared/ui/Table";
import { previousPeriod, summarizePeriod, periodChange, comparisonProfile } from "./periodComparisonData.mjs";

type Period = {start:string;end:string};
type History = {points:Record<string,unknown>[];interval_hours:number};
const rangeLabel = (period:Period) => [period.start,period.end].map(day=>new Date(`${day}T00:00:00`).toLocaleDateString("ru-RU")).join(" — ");
export function PeriodComparison({objectId,aggregateId,start,end,data,children}:{
  objectId:string;aggregateId:string;start:string;end:string;data?:History;children:ReactNode;
}) {
  const [manual,setManual] = useState<Period|null>(()=>{
    const params = new URL(location.href).searchParams;
    const start = params.get("base_start"), end = params.get("base_end");
    return start !== null && end !== null ? {start,end} : null;
  });
  const baseline = manual ?? previousPeriod(start,end);
  const duration = baseline ? (Date.parse(baseline.end)-Date.parse(baseline.start))/86400000 : NaN;
  const valid = Boolean(baseline?.start && baseline.end && Number.isFinite(duration) && duration >= 0 && duration <= 366);
  const selectedValid = Boolean(previousPeriod(start,end));
  const resource = useResource<History>(valid && selectedValid
    ? `/objects/${segment(objectId)}/timeline?start=${baseline!.start}&end=${baseline!.end}${aggregateId ? `&aggregate_id=${segment(aggregateId)}` : ""}` : null);
  function changeBaseline(value:Period|null) {
    setManual(value);
    const url = new URL(location.href);
    if (value) {url.searchParams.set("base_start",value.start);url.searchParams.set("base_end",value.end);}
    else {url.searchParams.delete("base_start");url.searchParams.delete("base_end");}
    window.history.replaceState(null,"",url);
  }
  const before = resource.data && valid ? summarizePeriod(resource.data.points,baseline!.start,baseline!.end,resource.data.interval_hours) : null;
  const after = data && selectedValid ? summarizePeriod(data.points,start,end,data.interval_hours) : null;
  const sameBasis = before && after && before.basis === after.basis && ["daily","interval"].includes(before.basis);
  const rows = before && after ? [
    {name: sameBasis && after.basis === "interval" ? "УРЭ по парным замерам, кВт·ч/м³" : "УРЭ по суммам, кВт·ч/м³",key:"sec", needsSameBasis:true},
    ...(before.basis === "daily" && after.basis === "daily" ? [{name:"Энергия по парным данным, кВт·ч",key:"energy"},{name:"Объём по парным данным, м³",key:"volume"}] : []),
    {name:"Расход, среднее замеров, м³/ч",key:"flow"},
    {name:"Мощность, среднее замеров, кВт",key:"power"},
    {name:"Давление на входе, среднее, МПа",key:"inlet"},
    {name:"Давление на выходе, среднее, МПа",key:"outlet"},
  ].map(metric=>{
    const a = before[metric.key as keyof typeof before], b = after[metric.key as keyof typeof after];
    const usable = !metric.needsSameBasis || sameBasis;
    return {name:metric.name,before:usable?a:null,after:usable?b:null,change:usable?periodChange(a,b):null};
  }) : [];
  const profiles = sameBasis && before!.paired > 0 && after!.paired > 0 && resource.data && data ? [
    {name:"А · База",start:baseline!.start,history:resource.data,color:"var(--chart-secondary)",dash:"dash"},
    {name:"Б · Выбрано",start,history:data,color:"var(--chart-primary)",dash:"solid"},
  ].map(period=>({...period,points:comparisonProfile(period.history.points,period.start,after!.basis,period.history.interval_hours)})) : [];
  const dates = profiles.map(profile=>new Map(profile.points.filter(p=>p.value!=null).map(p=>[p.day,p.timestamp])));
  const profileTraces:Trace[] = profiles.map(profile=>({
    type:"scatter",mode:"lines+markers",name:profile.name,
    x:profile.points.map(p=>new Date(Date.parse(`${start}T00:00:00`) + p.day * 86400000).toISOString()),y:profile.points.map(p=>p.value),
    hovertext:profile.points.map(p=>dates.map((values,i)=>{
      const timestamp=values.get(p.day);
      return `${profiles[i].name}: ${timestamp ? new Date(timestamp).toLocaleString("ru-RU") : "нет замера"}`;
    }).join("\n")),
    connectgaps:false,line:{color:profile.color,dash:profile.dash},marker:{size:4},
  }));
  const overlap = baseline && selectedValid && baseline.start <= end && baseline.end >= start;
  return <Panel title="Сравнение периодов" help="Сравнение описывает различия, а не устанавливает причину. Выбранный период задаётся на графиках. Базовый по умолчанию — предыдущий такой же длительности.">
    <details className="comparison-guide"><summary>Как сравнивать периоды</summary>
      <ol>
        <li><strong>Выберите период Б</strong> на графиках истории выше — тот, который хотите проверить.</li>
        <li><strong>Задайте базу А</strong> ниже. Лучше взять устойчивую работу того же оборудования при близкой подаче и требуемом давлении. По умолчанию выбраны предыдущие даты.</li>
        <li><strong>Посмотрите график и таблицу.</strong> График покажет момент и длительность отклонения, таблица — итоговые различия. Проверьте полноту данных и смену режима перед выводами.</li>
      </ol>
    </details>
    <div className="comparison-periods">
      <fieldset><legend>А · Базовый период</legend><div className="comparison-dates">
        <label>Начало<input aria-label="Начало базового периода" type="date" value={baseline?.start??""} onChange={e=>changeBaseline({start:e.target.value,end:baseline?.end??""})}/></label>
        <label>Конец<input aria-label="Конец базового периода" type="date" value={baseline?.end??""} onChange={e=>changeBaseline({start:baseline?.start??"",end:e.target.value})}/></label>
      </div>{manual && <Button variant="secondary" onClick={()=>changeBaseline(null)}>Предыдущий период</Button>}</fieldset>
      <div className="comparison-selected"><strong>Б · Выбранный период</strong><p>{selectedValid ? rangeLabel({start,end}) : "Выберите период на графиках"}</p><small>Задан на графиках выше</small></div>
    </div>
    {!valid && baseline && <p className="notice error" role="alert">Укажите базовый период от 1 до 367 дней. Начало должно быть не позже конца.</p>}
    {valid && selectedValid && <Status {...resource} />}
    {valid && before && after && <>
      <div className="comparison-state" role="status"><strong>Сопоставимость не подтверждена</strong><p>Нет подтверждённых данных о составе работающего оборудования, настройках управления и требуемом давлении. Изменение УРЭ не означает деградацию.</p></div>
      {!sameBasis && <p className="notice">Нет единой временной базы для сравнения УРЭ: детализация различается, смешана или измерений нет.</p>}
      {overlap && <p className="notice">Периоды пересекаются: часть измерений используется в обоих интервалах.</p>}
      {profileTraces.length > 0 && <section className="comparison-profile" aria-label="График сравнения УРЭ">
        <h3>УРЭ двух периодов</h3>
        <p className="muted">На оси X — даты по шкале периода Б. База А совмещена с ним по началу; в подсказке — реальные даты обоих периодов.</p>
        <Plot title="УРЭ двух периодов" data={profileTraces} layout={{height:280,showBrush:false,xaxis:{type:"date",title:{text:"Дата по шкале периода Б"}},yaxis:{title:{text:"кВт·ч/м³"}}}} />
      </section>}
      {sameBasis && !profileTraces.length && <p className="muted">Для графика нужны парные значения мощности и расхода либо энергии и объёма в обоих периодах.</p>}
      <div className="comparison-table"><Table rows={rows} columns={[{key:"name",label:"Показатель"},{key:"before",label:"А · База"},{key:"after",label:"Б · Выбрано"},{key:"change",label:"Изменение, %",digits:1}]} /></div>
      <div className="comparison-coverage" aria-label="Полнота данных">
        {[{name:"А",value:before},{name:"Б",value:after}].map(({name,value})=><p key={name}><strong>{name}</strong> · Парных значений УРЭ: {value.paired}{value.expected != null ? ` / ${value.expected} слотов периода` : ""}{value.stopped > 0 ? ` · Нулевая подача: ${value.stopped} замеров` : ""}</p>)}
      </div>
      <details><summary>Как рассчитано сравнение</summary><p>Суточный УРЭ — сумма энергии / сумма объёма только по дням с обоими значениями. Смешанная детализация не объединяется.</p><p>Для двухчасовых точек УРЭ — сумма мощностей / сумма расходов по парным замерам с положительной подачей. Это показатель выборки при одинаковом весе замеров, а не измеренная энергия и объём за период. Нулевая подача исключается из УРЭ.</p><p>Средние параметров рассчитаны отдельно по доступным замерам. Пропуски не заполняются. Число слотов относится ко всему календарному интервалу, включая ещё не наступившую часть текущего дня.</p></details>
    </>}
    {children}
  </Panel>;
}
