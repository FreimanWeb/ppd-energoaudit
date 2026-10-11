import { Plot, type Trace } from "../charts/Plot";
import type { TimeInteraction } from "../charts/types";
import { signalShape } from "./fidelity.mjs";

export type TelemetrySignal = {
  metric: string;
  unit: string;
  points: { timestamp: string; value: number | null }[];
};

export function TelemetryChart({
  title,
  series,
  timestamp,
  timeInteraction,
}: {
  title: string;
  series: TelemetrySignal[];
  timestamp?: string;
  timeInteraction?: TimeInteraction;
}) {
  const colors = [
    "var(--chart-primary)",
    "var(--chart-secondary)",
    "var(--chart-status-attention)",
  ];
  return (
    <div>
      <h3>{title}</h3>
      <Plot
        title={title}
        timeInteraction={timeInteraction}
        data={series.map((signal, index) => ({
          type: "scatter",
          mode: "lines+markers",
          name: signal.metric,
          x: signal.points.map((point) => point.timestamp),
          y: signal.points.map((point) => point.value),
          connectgaps: false,
          line: {
            color: colors[index % colors.length],
            shape: signalShape(signal.metric, signal.unit),
          },
        } as Trace))}
        layout={{
          yaxis: {
            title: { text: series[0].unit },
            gridcolor: "var(--chart-grid)",
          },
          xaxis: { type: "date", gridcolor: "var(--chart-grid)" },
          ...(timestamp ? {
            shapes: [{
              type: "line",
              xref: "x",
              x0: timestamp,
              x1: timestamp,
              yref: "paper",
              y0: 0,
              y1: 1,
              line: { color: "var(--chart-status-warning)", dash: "dot" },
            }],
          } : {}),
        }}
      />
    </div>
  );
}
