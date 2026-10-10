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
}: {
  power: number;
  losses: Loss[];
  status?: string;
  mode?: "decomposition" | "flow" | "percentage";
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
  return (
    <>
      {mode === "percentage" ? <LossPercentage power={power} losses={losses} /> : mode === "decomposition" ? <Plot
        title="Декомпозиция мощности"
        data={[chart.waterfall as Trace]}
        layout={{ height: 440, yaxis: { title: { text: "Мощность, кВт" } }, margin: { l: 65, r: 25, t: 20, b: 100 } }}
      /> : <Plot title="Поток мощности" data={[chart.sankey as Trace]} layout={{ height: 380, margin: { l: 15, r: 15, t: 15, b: 15 } }} />}
      {mode === "flow" && losses.some((x) => x.power_kw < 0) && (
        <p className="muted">
          Отрицательные составляющие показаны на диаграмме декомпозиции; поток
          мощности отображает только положительные значения.
        </p>
      )}
      <p className="muted">
        Подведённая мощность {fmt(power)} кВт · полезная{" "}
        {fmt(losses.find((x) => x.category === "полезная")?.power_kw)} кВт.
        <Tooltip label="Статьи потерь" content={<>Ширина потока соответствует мощности. Потери КПД — дополнительная мощность сверх паспортного состояния. Номинальные — базовые потери двигателя, насоса и передачи. Дросселирование — снижение давления арматурой. Гидравлические потери — сопротивление трубопровода и обвязки. Износ, неоптимальная подача и вязкость — составляющие ветки перекачки.</>} />
      </p>
    </>
  );
}
