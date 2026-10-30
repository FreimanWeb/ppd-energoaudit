import { segment,useResource } from "../../shared/api";
import type {Topology} from "../../shared/types";
import {Panel} from "../../shared/ui/Panel";
import {Status} from "../../shared/ui/Status";
import {MetricCard} from "../../shared/ui/MetricCard";
import {SchemePanel} from "../scheme/SchemePanel";
import {catalogMeasures,measureHref} from "../losses/measureCatalog.mjs";
import {MeasureCards} from "../losses/MeasureCards";
import {LinkButton} from "../../shared/ui/Button";
import "./overview.css";

type Summary={object_id:string;object_name:string;source:string;timestamp:string|null;aggregate_count:number;included_aggregates:string[];complete:boolean;warnings:string[];
  pressures:Record<string,{p_in_mpa:number;p_out_mpa:number}>;
  metrics:{flow_m3h:number|null;power_kw:number|null;sec_kwh_m3:number|null};
  annual:{efficiency_energy_kwh:number|null;efficiency_money_krub:number|null;throttle_energy_kwh:number|null;throttle_money_krub:number|null}|null;
  measures?:Parameters<typeof catalogMeasures>[0];annual_basis?:string|null;network?:Parameters<typeof SchemePanel>[0]["stationNetwork"];
};
export function StationOverview({objectId,source,topology}:{objectId:string;source:"telemetry"|"field_trip";topology?:Topology}){
  const summary=useResource<Summary>(`/objects/${segment(objectId)}/station-summary`,JSON.stringify({source}));
  const data=summary.data;
  const warnings=[...new Set([...(data?.warnings??[]),...(data?.network?.warnings??[])])];
  return <div className="overview-page">
    <Status {...summary}/>
    {data&&<>
      {!data.complete&&<p className="notice" role="status">Для полной сводки станции не хватает сопоставимых данных всех НА. Неполные суммы не показаны.</p>}
      <Panel title="Показатели станции" action={<div className="station-context"><span>Учтено НА: {data.included_aggregates.length} из {data.aggregate_count}</span>{data.timestamp?<time dateTime={data.timestamp}>{new Date(data.timestamp).toLocaleString("ru-RU")}</time>:<span>Выездные данные</span>}</div>}>
        <div className="station-kpis">
          <MetricCard label="УРЭ станции" value={data.metrics.sec_kwh_m3} unit="кВт·ч/м³" help="Сумма электрических мощностей / сумма расходов всех учтённых НА на общий момент измерения. КПД отдельных насосов не усредняется."/>
          <MetricCard label="Расход станции" value={data.metrics.flow_m3h} unit="м³/ч" help="Сумма расходов НА на общий момент измерения."/>
          <MetricCard label="Мощность станции" value={data.metrics.power_kw} unit="кВт" help="Суммарная электрическая мощность учтённых НА."/>
          <MetricCard label="Потери до устьев · оценка" value={data.network?.status === "scenario" ? data.network.operator_balance?.total_loss_kw : null} unit="кВт" help="Сценарная сумма потерь до устьев после штуцеров, как в графе ниже. Трение в стволах находится за этой границей. Выходная мощность исключена. Это не подтверждённый потенциал экономии; без полного баланса оценка отсутствует."/>
        </div>
      </Panel>
      <SchemePanel station topology={topology} stationNetwork={data.network} pressures={data.pressures}/>
      <Panel title="Годовая оценка · сценарий" help={data.annual_basis||"Оценка работы при сохранении текущего режима и принятой годовой наработке. Это стоимость потерь, а не подтверждённая экономия мероприятия."}>
        <div className="station-annual">
          <MetricCard label="Потери по КПД" value={null} unit="" help="Сумма индивидуальных годовых оценок по всем учтённым НА. Не среднее их КПД." segments={[
            {label:"Энергия",value:data.annual?.efficiency_energy_kwh,unit:"кВт·ч/год",help:"Сценарная годовая энергия потерь из-за снижения КПД."},
            {label:"Стоимость",value:data.annual?.efficiency_money_krub,unit:"тыс. ₽/год",help:"Стоимость энергии потерь по тарифу. Не затраты на мероприятие."},
          ]}/>
          <MetricCard label="Потери дросселирования" value={null} unit="" help="Насос создаёт избыточное давление, которое затем снижается на арматуре до БГ. Энергия этого перепада рассеивается; она не является полезной закачкой и не обязательно может быть устранена целиком." segments={[
            {label:"Энергия",value:data.annual?.throttle_energy_kwh,unit:"кВт·ч/год",help:"Сценарная энергия потерь из-за перепада давления до БГ."},
            {label:"Стоимость",value:data.annual?.throttle_money_krub,unit:"тыс. ₽/год",help:"Стоимость энергии потерь по тарифу; достижимость экономии требует проверки."},
          ]}/>
        </div>
        {data.annual_basis&&<p className="muted">{data.annual_basis}</p>}
        {!data.annual&&<p className="muted">Недостаточно согласованных данных для годовой оценки всей станции.</p>}
      </Panel>
    </>}
    {data&&<Panel title="Мероприятия по годовой экономии" action={<LinkButton href={measureHref(null,"")}> Все мероприятия</LinkButton>}>
      <MeasureCards actions={catalogMeasures(data.measures ?? []).slice(0,3)}
        context={{objectId,source,aggregateId:"",timestamp:data.timestamp ?? ""}}/>
      {(data.measures?.length ?? 0)>0 ? <p className="muted">Годовые оценки мероприятий отдельных НА. Эффекты не суммируются.</p>
        : <div className="content-actions"><p>Недостаточно сопоставимых данных для оценки эффекта мероприятий.</p><LinkButton href="#sources">Проверить исходные данные</LinkButton></div>}
    </Panel>}
    {!data&&<SchemePanel station topology={topology}/>}
    {warnings.length?<details><summary>Данные и расчёт</summary><ul>{warnings.map((warning,i)=><li key={i}>{warning}</li>)}</ul></details>:null}
  </div>;
}
