import {lossLabel,lossLabels} from "../../shared/lossLabels";
import { Plot, type Trace } from "../../charts/Plot";
import { fmt } from "../../shared/ui/format";
import { Tooltip } from "../../shared/ui/Tooltip";
import { lossChartData } from "../../pages/lossChartData.mjs";
import { LossPercentage } from "./LossPercentage";

export type Loss = { name: string; power_kw: number; share: number; category: string };

export function LossCharts({
  power,
  losses,
  status,
  mode = "decomposition",
  onSelect,
  showSummary = true,
  inputLabel,
  axisLabels,
  groups,
}: {
  power: number;
  losses: Loss[];
  status?: string;
  mode?: "decomposition" | "percentage";
  onSelect?: (name: string) => void;
  showSummary?: boolean;
  inputLabel?: string;
  axisLabels?: Record<string, string>;
  groups?: {label:string;names:string[]}[];
}) {
  if (status === "unfit")
    return (
      <p className="notice error">
        Карта потерь не построена: выбранный режим непригоден для достоверных
        выводов.
      </p>
    );
  if (!losses.length)
    return <p className="notice">Декомпозиция для выбранного режима недоступна.</p>;
  const label=(name:string)=>axisLabels?.[name] ?? lossLabel(name);
  const displayed=losses.map(item=>({...item,name:label(item.name)}));
  const select=(name:string)=>onSelect?.(losses.find(item=>label(item.name) === name)?.name ?? name);
  const chart = lossChartData(power, displayed, inputLabel ?? lossLabels.input);
  const categoryGroups=groups?.flatMap(group=>{
    const names=losses.filter(item=>group.names.includes(item.name)).map(item=>item.name);
    return names.length ? [{label:group.label,from:label(names[0]),to:label(names.at(-1)!)}] : [];
  });
  return (
    <>
      {mode === "percentage" ? <LossPercentage basisLabel={inputLabel === lossLabels.bg ? "гидравлической мощности на БГ" : undefined} power={power} losses={displayed.filter(item=>item.category !== "промежуточная")} onSelect={select} /> : <Plot
        onSelect={select}
        title="Декомпозиция мощности"
        data={[chart.waterfall as Trace]}
        layout={{ categoryGroups, height: 440, yaxis: { title: { text: "Мощность, кВт" } }, margin: { l: 65, r: 25, t: 20, b: 100 } }}
      />}
      {showSummary && <p className="muted">
        {lossLabels.input} {fmt(power)} кВт · {lossLabels.useful.toLowerCase()}
        {fmt(losses.find((x) => x.category === "полезная")?.power_kw)} кВт.
        <Tooltip label="Статьи потерь" content={<>{lossLabels.efficiency} — дополнительная мощность сверх паспортного состояния. {lossLabels.nominal} — базовые потери двигателя, насоса и передачи. {lossLabels.na_throttle} — дополнительная мощность НА из-за снижения давления перед БГ. {lossLabels.hydraulic_bg} — потеря гидравлической мощности между выкидом насоса и БГ.</>} />
      </p>}
    </>
  );
}
