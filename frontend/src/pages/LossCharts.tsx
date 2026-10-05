import { Plot, type Trace } from "../Plot";
import { fmt } from "./common";
import { lossChartData } from "./lossChartData.mjs";
type Loss = { name: string; power_kw: number; share: number; category: string };
export function LossCharts({
  power,
  losses,
  status,
  compact = false,
}: {
  power: number;
  losses: Loss[];
  status?: string;
  compact?: boolean;
}) {
  if (status === "unfit")
    return (
      <p className="notice error">
        Карта потерь не построена: выбранный режим непригоден для достоверных
        выводов.
      </p>
    );
  if (!losses.length)
    return (
      <p className="notice">Декомпозиция для выбранного режима недоступна.</p>
    );
  const chart = lossChartData(power, losses);
  if (compact)
    return (
      <Plot
        title="Структура подведённой мощности"
        data={chart.shares as Trace[]}
        layout={{
          barmode: "relative",
          height: 180,
          xaxis: { title: { text: "Доля от подведённой мощности, %" } },
          yaxis: { visible: false },
          margin: { l: 20, r: 20, t: 15, b: 65 },
        }}
      />
    );
  return (
    <>
      <Plot
        title="Декомпозиция мощности"
        data={[chart.waterfall as Trace]}
        layout={{
          height: 440,
          yaxis: { title: { text: "Мощность, кВт" } },
          margin: { l: 65, r: 25, t: 20, b: 100 },
        }}
      />
      <Plot
        title="Поток мощности"
        data={[chart.sankey as Trace]}
        layout={{ height: 380, margin: { l: 15, r: 15, t: 15, b: 15 } }}
      />
      {losses.some((x) => x.power_kw < 0) && (
        <p className="muted">
          Отрицательные составляющие показаны на диаграмме декомпозиции; поток
          мощности отображает только положительные значения.
        </p>
      )}
      <p className="muted">
        Подведённая мощность {fmt(power)} кВт · полезная{" "}
        {fmt(losses.find((x) => x.category === "полезная")?.power_kw)} кВт.
        Ширина потока соответствует мощности.
      </p>
      <details>
        <summary>Расшифровка статей потерь</summary>
        <p>
          Потери КПД — дополнительная мощность сверх паспортного состояния.
          Номинальные — базовые потери двигателя, насоса и передачи.
          Дросселирование — снижение давления арматурой. Гидравлические потери —
          сопротивление трубопровода и обвязки. Износ, неоптимальная подача и
          вязкость — составляющие ветки перекачки.
        </p>
      </details>
    </>
  );
}
export function EfficiencyCharts({
  metrics,
  target,
}: {
  metrics: Record<string, number | null>;
  target?: number | null;
}) {
  const nominal = metrics.eta_nom,
    actual = metrics.eta_unit;
  const top = Math.max(nominal ?? 0, actual ?? 0) * 1.15;
  return (
    <div className="chart-grid">
      {nominal !== null && actual !== null && nominal > 0 && (
        <Plot
          title="КПД установки"
          data={[
            {
              type: "indicator",
              mode: "gauge+number",
              value: actual,
              number: { valueformat: ".3f" },
              title: { text: "КПД установки (факт)" },
              gauge: {
                axis: { range: [0, top] },
                bar: { color: "#1f4e4a" },
                steps: [
                  { range: [0, nominal * 0.78], color: "#f6d6d2" },
                  { range: [nominal * 0.78, nominal * 0.9], color: "#fdeecb" },
                  { range: [nominal * 0.9, top], color: "#cdeedd" },
                ],
                threshold: {
                  line: { color: "#426b80", width: 4 },
                  value: nominal,
                },
              },
            },
          ]}
          layout={{ height: 270, margin: { l: 25, r: 25, t: 45, b: 20 } }}
        />
      )}
      <Plot
        title="Сравнение удельного расхода энергии"
        data={[
          {
            type: "bar",
            x: [
              "Факт",
              "Расчётный",
              "Оптимальный",
              ...(target != null ? ["Цель-2035"] : []),
            ],
            y: [
              metrics.sec_fact_kwh_m3,
              metrics.sec_calc_kwh_m3,
              metrics.sec_optimal_kwh_m3,
              ...(target != null ? [target] : []),
            ],
            marker: { color: ["#c76e62", "#426b80", "#1f4e4a", "#8b9892"] },
          },
        ]}
        layout={{ height: 270, yaxis: { title: { text: "УРЭ, кВт·ч/м³" } } }}
      />
    </div>
  );
}
