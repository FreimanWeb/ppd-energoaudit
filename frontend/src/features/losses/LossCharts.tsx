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
  axisLabels,
  groups,
}: {
  power: number;
  losses: Loss[];
  status?: string;
  mode?: "decomposition" | "flow" | "percentage";
  onSelect?: (name: string) => void;
  showSummary?: boolean;
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
  const chart = lossChartData(power, losses);
  const categoryGroups=groups?.flatMap(group=>{
    const names=chart.waterfall.x.filter(name=>group.names.includes(name));
    return names.length ? [{label:group.label,from:axisLabels?.[names[0]] ?? names[0],to:axisLabels?.[names.at(-1)!] ?? names.at(-1)!}] : [];
  });
  if (axisLabels) {
    chart.waterfall.tooltip = chart.waterfall.tooltip.map((point, index) => ({ ...point, selection: chart.waterfall.x[index] }));
    chart.waterfall.x = chart.waterfall.x.map(label => axisLabels[label] ?? label);
  }
  return (
    <>
      {mode === "percentage" ? <LossPercentage power={power} losses={losses} onSelect={onSelect} /> : mode === "decomposition" ? <Plot
        onSelect={onSelect}
        title="Декомпозиция мощности"
        data={[chart.waterfall as Trace]}
        layout={{ categoryGroups, height: 440, yaxis: { title: { text: "Мощность, кВт" } }, margin: { l: 65, r: 25, t: 20, b: 100 } }}
      /> : <Plot onSelect={onSelect} title="Поток мощности" data={[chart.sankey as Trace]} layout={{ height: 380, margin: { l: 15, r: 15, t: 15, b: 15 } }} />}
      {mode === "flow" && losses.some((x) => x.power_kw < 0) && (
        <p className="muted">
          Отрицательные составляющие показаны на диаграмме декомпозиции; поток
          мощности отображает только положительные значения.
        </p>
      )}
      {showSummary && <p className="muted">
        Подведённая мощность {fmt(power)} кВт · полезная{" "}
        {fmt(losses.find((x) => x.category === "полезная")?.power_kw)} кВт.
        <Tooltip label="Статьи потерь" content={<>Ширина потока соответствует мощности. Потери КПД — дополнительная мощность сверх паспортного состояния. Номинальные — базовые потери двигателя, насоса и передачи. Дросселирование — снижение давления арматурой. Гидравлические потери — сопротивление трубопровода и обвязки. Износ, неоптимальная подача и вязкость — составляющие ветки перекачки.</>} />
      </p>}
    </>
  );
}
