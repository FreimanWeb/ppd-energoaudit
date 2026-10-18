import type { ReactNode } from "react";
import type { Audit, Topology } from "../../shared/types";
import { fmt } from "../../shared/ui/format";
import { Scheme } from "./Scheme";
import { segment, useResource } from "../../shared/api";
import { networkStages, stageDefinitions } from "../losses/networkStages.mjs";
import "./schemeLosses.css";

export function SchemePanel({topology,audit,aggregate="",pressures,status,station=false,stationNetwork}: {
  topology?: Topology; audit?: Audit; aggregate?: string;
  station?:boolean;stationNetwork?:Parameters<typeof networkStages>[0] & {warnings?:string[];network?:{well_count?:number}};
  pressures?: Record<string,{p_in_mpa:number;p_out_mpa:number}>; status?: ReactNode;
}) {
  const timestamp = audit?.snapshot?.timestamp;
  const supported = ["kns54an","demo-ppd"].includes(audit?.audit.object_id ?? "");
  const network = useResource<Parameters<typeof networkStages>[0] & {network?:{well_count?:number}}>(
    !station && supported && audit && audit.quality.status !== "unfit" && (audit?.source === "field_trip" || timestamp)
      ? `/objects/${segment(audit?.audit.object_id)}/aggregates/${segment(aggregate)}/network-losses` : null,
    JSON.stringify({source:audit?.source,...(audit?.source === "telemetry" && timestamp ? {day:timestamp.slice(0,10),timestamp} : {})}),
  );
  const map = station ? stationNetwork : network.data;
  const stages = networkStages(map);
  const areas = stageDefinitions.map(definition => stages.find(stage => stage.id === definition.id)
    ?? {id:definition.id,label:definition.label,power_kw:null,share_pct:null});
  const wellCount = map?.network?.well_count;
  return <section className="scheme-panel" aria-label="Условная технологическая схема ППД">
    <div className="section-heading"><h2>Условная технологическая схема ППД</h2></div>
    <p className="scheme-source">Скважины и водоводы показаны условно группами. Наведите на участок или карточку, нажмите для подробностей.</p>
    {status}
    {topology && <>
      <div className="scheme-layout"><div className="scheme-canvas">
        <Scheme topology={topology} aggregate={aggregate} audit={station?undefined:audit} pressures={pressures} lossStages={areas} wellCount={typeof wellCount === "number" && wellCount > 0 ? wellCount : undefined} />
      </div></div>
      {stages.length > 0
        ? <p className="scheme-source">100 % — сумма потерь всей цепочки ({fmt(map?.total_loss_kw,1)} кВт), без полезной мощности. Сценарная оценка: параметры внешней сети частично синтетические. {station ? "Учтены совместно работающие НА станции." : "Сценарий выбранного НА; остальные насосы в сценарии выключены."} Арматура сети включена в группу скважин. Нормы потерь по участкам для цветовой оценки пока не заданы.</p>
        : <p className="scheme-source" role="status">{network.loading ? "Рассчитываем доли потерь…" : network.error ? `Распределение потерь недоступно: ${network.error}` : "Доли потерь недоступны для выбранного режима. Откройте участок для просмотра имеющихся данных."}</p>}
      <p className="scheme-source">Источник схемы: {topology.source}</p>
    </>}
  </section>;
}
