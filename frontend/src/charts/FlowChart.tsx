import { ParentSize } from "@visx/responsive";
import { sankey, sankeyLinkHorizontal, type SankeyNode } from "d3-sankey";
import type { SankeyModel } from "./types";
import { activeFlowGraph, flowNodeValues } from "./specialChartData.mjs";
import "./specialCharts.css";

type FlowNode = { name: string; color: string; originalIndex: number };
type FlowLink = { color: string };
const number = (value: number) => new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value);

export function FlowChart({ model }: { model: SankeyModel }) {
  const links = model.links.filter(link => link.value > 0);
  const height = Math.max(model.height, links.length * 58 + 70);
  const totals = flowNodeValues(model.nodes.length, links);
  const activeGraph = activeFlowGraph(model.nodes, links);
  if (!links.length) return <p className="muted">Нет положительных потоков мощности.</p>;
  return <div className="flow-chart">
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
            {graph.links.map((link, i) => <path key={i} className="flow-link" d={path(link) ?? ""}
              fill="none" stroke={link.color} strokeWidth={Math.max(link.width ?? 0, .5)} opacity={.48}>
              <title>{(link.source as SankeyNode<FlowNode, FlowLink>).name} → {(link.target as SankeyNode<FlowNode, FlowLink>).name}: {number(link.value)} кВт</title>
            </path>)}
            {graph.nodes.map((node, i) => {
              const input = !!node.sourceLinks?.length;
              return <g className="flow-node" key={i}>
                <title>{node.name}{totals[node.originalIndex] === null ? "" : `: ${number(totals[node.originalIndex])} кВт`}</title>
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
    <ul className="flow-legend" aria-label="Состав потока мощности">
      {model.nodes.map((item, index) => (totals[index] === null || totals[index] > 0) && <li key={index}>
        <span className="chart-color-key" style={{ backgroundColor: item.color }} />
        <span>{item.name}</span>{totals[index] !== null && <strong>{number(totals[index])} кВт</strong>}
      </li>)}
    </ul>
  </div>;
}
