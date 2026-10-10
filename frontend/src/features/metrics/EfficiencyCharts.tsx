import { Plot } from "../../charts/Plot";
import { metricAssessment } from "../../shared/metrics/metricAssessment.mjs";

const toneColor = (tone: string) => tone === "bad" ? "var(--chart-status-danger)" : tone === "good" ? "var(--chart-status-success)" : "var(--chart-status-neutral)";

export function EfficiencyCharts({ metrics, usable = true }: {
  metrics: Record<string, number | null>; usable?: boolean; target?: number | null;
}) {
  const nominal = metrics.eta_nom, actual = metrics.eta_unit;
  const top = 1;
  const efficiencyTone = metricAssessment(actual, nominal, "lower", usable, true).tone;
  if (nominal == null || actual == null || nominal <= 0) return null;
  return (
    <Plot
      title="КПД установки"
      data={[{
        type: "indicator",
        mode: "gauge+number",
        value: Math.max(0, Math.min(1, actual)),
        number: { valueformat: ".3f" },
        title: { text: "КПД установки (факт)" },
        gauge: {
          axis: { range: [0, top] },
          bar: { color: toneColor(efficiencyTone) },
          steps: [
            { range: [0, Math.min(1, nominal * 0.78)], color: "var(--chart-status-danger-soft)" },
            { range: [Math.min(1, nominal * 0.78), Math.min(1, nominal * 0.9)], color: "var(--chart-status-warning-soft)" },
            { range: [Math.min(1, nominal * 0.9), 1], color: "var(--chart-status-success-soft)" },
          ],
          threshold: { line: { color: "var(--chart-secondary)", width: 4 }, value: Math.min(1, nominal) },
        },
      }]}
      layout={{ height: 270, margin: { l: 25, r: 25, t: 45, b: 20 } }}
    />
  );
}
