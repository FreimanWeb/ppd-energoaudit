import { useState } from "react";
import { ParentSize } from "@visx/responsive";
import { scaleLinear } from "@visx/scale";
import { LinePath } from "@visx/shape";
import type { NetworkModel } from "./types";
import { chartTheme } from "./theme";
import "./specialCharts.css";

export function NetworkChart({ model, onSelect }: { model: NetworkModel; onSelect?: (label: string) => void }) {
  const [focused, setFocused] = useState<string | null>(null);
  const focusedNode = model.nodes.find(node => node.id === focused);
  const focusedEdges = model.edges.filter(edge => edge.source === focused || edge.target === focused);
  const xs = model.nodes.map(node => node.x), ys = model.nodes.map(node => node.y);
  const xLow = Math.min(...xs), xHigh = Math.max(...xs), yLow = Math.min(...ys), yHigh = Math.max(...ys);
  const xPad = Math.max(xHigh - xLow, 1) * .1, yPad = Math.max(yHigh - yLow, 1) * .1;
  return <div className="network-chart">
    <div style={{ height: model.height }}>
      <ParentSize debounceTime={0} ignoreDimensions={["height"]}>
        {({ width }) => {
          if (!width || !model.nodes.length) return null;
          const x = scaleLinear({ domain: [xLow - xPad, xHigh + xPad], range: [28, width - 28] });
          const y = scaleLinear({ domain: [yLow - yPad, yHigh + yPad], range: [model.height - 24, 32] });
          return <svg className="visx-chart visx-network" width={width} height={model.height} role="group" aria-label="Граф скважин">
            {model.edges.map((edge, i) => <LinePath key={i} className="network-edge" data={edge.points}
              x={point => x(point.x)} y={point => y(point.y)} stroke={edge.color} strokeWidth={edge.width}
              fill="none" pointerEvents="none" />)}
            {model.nodes.map(node => {
              const cx = x(node.x), cy = y(node.y), radius = Math.max(7, node.size / 2);
              return <g className="network-node" key={node.id} role="button" tabIndex={0}
                aria-label={`Скважина ${node.label}`} aria-pressed={node.size > 12}
                onClick={() => onSelect?.(node.id)}
                onKeyDown={event => {
                  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect?.(node.id); }
                }}
                onFocus={() => setFocused(node.id)} onBlur={() => setFocused(null)}
                onMouseEnter={() => setFocused(node.id)} onMouseLeave={() => setFocused(null)}>
                <title>{node.label}: {node.detail}</title>
                <rect className="network-hit-area" x={cx - Math.max(22, node.label.length * 4)}
                  y={cy - radius - 24} width={Math.max(44, node.label.length * 8)}
                  height={radius * 2 + 28} fill="transparent" pointerEvents="all" />
                {node.shape === "square" ?
                  <rect className="network-marker" x={cx - radius} y={cy - radius} width={radius * 2} height={radius * 2} rx={2} fill={node.color} stroke="white" strokeWidth={2} /> :
                  <circle className="network-marker" cx={cx} cy={cy} r={radius} fill={node.color} stroke="white" strokeWidth={2} />}
                <text x={cx} y={cy - radius - 7} textAnchor="middle" fill={chartTheme.text} fontSize={12}>{node.label}</text>
              </g>;
            })}
          </svg>;
        }}
      </ParentSize>
    </div>
    <div className="network-tooltip" role="status" aria-live="polite">
      {focusedNode ? <><strong>Скважина {focusedNode.label}</strong><span>{focusedNode.detail}</span>
        {focusedEdges.map((edge, i) => <span key={i}>{edge.label}</span>)}</> : <span>Выберите скважину на графе или клавишей Enter.</span>}
    </div>
  </div>;
}
