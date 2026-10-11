import { useState } from "react";
import { ChartTooltip } from "./ChartTooltip";
import { ParentSize } from "@visx/responsive";
import { sankey, sankeyLinkHorizontal, type SankeyNode } from "d3-sankey";
import type { SankeyModel } from "./types";
import { activeFlowGraph, flowNodeValues } from "./specialChartData.mjs";
import "./specialCharts.css";

type FlowNode = SankeyModel["nodes"][number] & { originalIndex: number };
type FlowLink = { color: string; tooltip?: SankeyModel["links"][number]["tooltip"] };
const number = (value: number) => new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value);

export function FlowChart({ model, onSelect }: { model: SankeyModel; onSelect?: (id: string) => void }) {
  const [tip, setTip] = useState<{ title: string; value: number; unit?: string; share?: number; x: number; y: number } | null>(null);
  function inspect(event: React.MouseEvent<SVGElement> | React.FocusEvent<SVGElement>, title: string, value: number, metadata?: SankeyModel["nodes"][number]["tooltip"]) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const parent = event.currentTarget.closest(".flow-chart")!.getBoundingClientRect();
    setTip({ title, value: metadata?.value ?? value, unit: metadata?.unit ?? "кВт", share: metadata?.share, x: Math.max(8, Math.min(parent.width - 230, bounds.left - parent.left)), y: bounds.top - parent.top });
  }
  const activate = (selection?: string) => selection && onSelect?.(selection);
  const keyboard = (event: React.KeyboardEvent, selection?: string) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); activate(selection); } };
  const links = model.links.filter(link => link.value > 0);
  const height = Math.max(model.height, links.length * 58 + 70);
  const totals = flowNodeValues(model.nodes.length, links);
  const activeGraph = activeFlowGraph(model.nodes, links);
  if (!links.length) return <p className="muted">Нет положительных потоков мощности.</p>;
  return <div className="flow-chart" style={{ position: "relative" }} onMouseLeave={() => setTip(null)}>
    <div style={{ height }}>
      <ParentSize debounceTime={0} ignoreDimensions={["height"]}>
        {({ width }) => {
          if (width < 30) return null;
          const graph = sankey<FlowNode, FlowLink>().nodeWidth(14).nodePadding(32).nodeSort(null)
            .extent([[12, 20], [width - 12, height - 20]])({
              nodes: activeGraph.nodes.map((node: FlowNode) => ({ ...node })), links: activeGraph.links.map((link: SankeyModel["links"][number]) => ({ ...link })),
            });
          const path = sankeyLinkHorizontal<FlowNode, FlowLink>();
          const labelWidth = Math.max(1, Math.min(100, (width - 84) / 2));
          return <svg className="visx-chart visx-flow" width={width} height={height} role="img" aria-label={model.title}>
            {graph.links.map((link, i) => {
              const target = link.target as SankeyNode<FlowNode, FlowLink>;
              return <path key={i} className="flow-link" d={path(link) ?? ""}
                role={link.tooltip?.selection ? "button" : undefined} tabIndex={0} aria-label={`${target.name}: ${number(link.value)} кВт`}
                onMouseEnter={event => inspect(event, target.name, link.value, link.tooltip)}
                onFocus={event => inspect(event, target.name, link.value, link.tooltip)} onBlur={() => setTip(null)}
                onClick={() => activate(link.tooltip?.selection)} onKeyDown={event => keyboard(event, link.tooltip?.selection)}
                fill="none" stroke={link.color} strokeWidth={Math.max(link.width ?? 0, .5)} opacity={.48} />;
            })}
            {graph.nodes.map((node, i) => {
              const input = !!node.sourceLinks?.length;
              return <g className="flow-node" key={i} tabIndex={0} role={node.tooltip?.selection ? "button" : undefined} aria-label={node.name}
                onMouseEnter={event => inspect(event, node.name, totals[node.originalIndex] ?? 0, node.tooltip)}
                onFocus={event => inspect(event, node.name, totals[node.originalIndex] ?? 0, node.tooltip)} onBlur={() => setTip(null)}
                onClick={() => activate(node.tooltip?.selection)} onKeyDown={event => keyboard(event, node.tooltip?.selection)}>
                <rect x={node.x0} y={node.y0} width={node.x1! - node.x0!} height={node.y1! - node.y0!} rx={3} fill={node.color} />
                <foreignObject x={input ? node.x1! + 8 : node.x0! - labelWidth - 8}
                  y={(node.y0! + node.y1!) / 2 - 24} width={labelWidth} height={56}>
                  <div className="flow-node-label" style={{ textAlign: input ? "left" : "right" }}>{node.name}</div>
                </foreignObject>
              </g>;
            })}
          </svg>;
        }}
      </ParentSize>
    </div>
    {tip && <ChartTooltip title={tip.title} rows={[{ value: tip.value, unit: tip.unit, share: tip.share }]} style={{ left: tip.x, top: Math.max(4, tip.y - 20) }} />}
    <ul className="flow-legend" aria-label="Состав потока мощности">
      {model.nodes.map((item, index) => (totals[index] === null || totals[index] > 0) && <li key={index}>
        <span className="chart-color-key" style={{ backgroundColor: item.color }} />
        <span>{item.name}</span>{totals[index] !== null && <strong>{number(totals[index])} кВт</strong>}
      </li>)}
    </ul>
  </div>;
}
