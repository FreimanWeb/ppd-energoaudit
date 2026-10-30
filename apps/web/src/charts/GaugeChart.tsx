import { ParentSize } from "@visx/responsive";
import { Arc } from "@visx/shape";
import type { GaugeModel } from "./types";
import { chartTheme } from "./theme";
import { gaugePoint } from "./specialChartData.mjs";
import "./specialCharts.css";

const number = (value: number) => new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 }).format(value);

export function GaugeChart({ model }: { model: GaugeModel }) {
  const height = Math.min(220, model.height);
  const [low, high] = model.range;
  const extent = Math.max(high - low, Number.EPSILON);
  const ratio = (value: number) => Math.max(0, Math.min(1, (value - low) / extent));
  const angle = (value: number) => -Math.PI / 2 + Math.PI * ratio(value);
  const label = `Фактический КПД ${number(model.value)}${model.threshold === undefined ? "" : `; номинальный ${number(model.threshold)}`}`;
  const bands = model.steps.length ? model.steps : [{ range: model.range, color: "var(--chart-grid)" }];
  return <div className="gauge-chart" role="img" aria-label={label}>
    <div style={{ height }}>
      <ParentSize debounceTime={0} ignoreDimensions={["height"]}>
        {({ width }) => {
          if (!width) return null;
          const cx = width / 2, cy = height * .64;
          const radius = Math.max(15, Math.min(width / 2 - 25, height * .52));
          const tip = gaugePoint(model.value - low, extent, 0, 0, radius - 34);
          const marker = model.threshold === undefined ? undefined : gaugePoint(model.threshold - low, extent, 0, 0, radius + 4);
          const markerInner = model.threshold === undefined ? undefined : gaugePoint(model.threshold - low, extent, 0, 0, radius - 27);
          return <svg className="visx-chart visx-gauge" width={width} height={height} aria-hidden="true">
            <g transform={`translate(${cx},${cy})`}>
              {bands.map((band, i) => <Arc key={i} className="gauge-band"
                innerRadius={radius - 22} outerRadius={radius} fill={band.color}
                startAngle={angle(band.range[0])} endAngle={angle(band.range[1])} />)}
              <Arc innerRadius={radius - 33} outerRadius={radius - 27} fill={chartTheme.grid}
                startAngle={-Math.PI / 2} endAngle={Math.PI / 2} />
              <Arc innerRadius={radius - 33} outerRadius={radius - 27} fill={model.color}
                startAngle={-Math.PI / 2} endAngle={angle(model.value)} />
              <g className="gauge-overlay">
                {marker && markerInner && <line x1={marker.x} y1={marker.y}
                  x2={markerInner.x} y2={markerInner.y} stroke={model.thresholdColor} strokeWidth={3}>
                  <title>Номинальный КПД: {number(model.threshold!)}</title>
                </line>}
                <line x1={0} y1={0} x2={tip.x} y2={tip.y} stroke={model.color} strokeWidth={3} strokeLinecap="round" />
                <circle cx={0} cy={0} r={5} fill={model.color} />
                <text className="gauge-value" x={0} y={32} textAnchor="middle" fill={model.color} fontSize={25} fontWeight={650}>{number(model.value)}</text>
                <text x={-radius} y={20} textAnchor="start" fill={chartTheme.text} fontSize={11}>{number(low)}</text>
                <text x={radius} y={20} textAnchor="end" fill={chartTheme.text} fontSize={11}>{number(high)}</text>
              </g>
            </g>
          </svg>;
        }}
      </ParentSize>
    </div>
  </div>;
}
