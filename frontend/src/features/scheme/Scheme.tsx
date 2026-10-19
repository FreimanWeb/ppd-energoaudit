import { type CSSProperties } from "react";
import symbols from "../../../../shared/ppd-symbols.svg?raw";
import { layoutTopology } from "./scheme.mjs";
import type { Audit, Topology } from "../../shared/types";

export function Scheme({
  topology,
  aggregate,
  audit,
  activeStage,
  onStageHover,
  onStageFocus,
  wellCount,
}: {
  topology: Topology;
  aggregate: string;
  audit?: Audit;
  pressures?: Record<string, {p_in_mpa: number; p_out_mpa: number}>;
  activeStage?:string|null;
  onStageHover?:(id:string|null)=>void;
  onStageFocus?:(id:string|null)=>void;
  wellCount?: number;
}) {
  const interaction = (id:string) => ({
    "data-stage":id,"data-active":activeStage===id?true:undefined,
    onPointerEnter:()=>onStageHover?.(id),onPointerLeave:()=>onStageHover?.(null),
    onFocus:()=>onStageFocus?.(id),onBlur:()=>onStageFocus?.(null),
  });
  const graph = layoutTopology(topology);
  const pipeEdge = graph.edges.find(edge => edge.source.type === "manifold" && edge.target.type === "valve");
  const wells = graph.nodes.find(node => node.type === "wells");
  const pumps = graph.nodes.filter((n) => n.type === "pump");
  const x0 = Math.min(...pumps.map((n) => n.px)) - 100;
  const y0 = Math.min(...pumps.map((n) => n.py)) - 70;
  return (
    <div className="scheme-stage">
      <svg
        className="equipment-scheme"
        viewBox={`0 0 ${graph.width} ${graph.height}`}
        aria-label="Условная технологическая схема ППД"
      >
        <title>Оборудование, водоводы, скважины и пласт</title>
        <g dangerouslySetInnerHTML={{ __html: symbols }} />
        <g>
          {pipeEdge && <a href="#pipelines" aria-label="Открыть трубопроводы" className="scheme-area-link" {...interaction("pipes")}>
            <rect x={pipeEdge.source.px + 56} y={pipeEdge.source.py - 50} width={Math.max(40,pipeEdge.target.px - pipeEdge.source.px - 96)} height="100" rx="10" fill="var(--surface-subtle)" stroke="var(--border)" />
          </a>}
          {wells && <a href="#wells" aria-label="Открыть скважины" className="scheme-area-link" {...interaction("wells")}>
            <rect x={wells.px - 90} y={wells.py - 60} width="180" height="250" rx="10" fill="var(--surface-subtle)" stroke="var(--border)" />
          </a>}
          {pumps.length > 0 && (
            <a href="#machine-block" aria-label="Открыть машинный блок" className="scheme-area-link" {...interaction("hall")}>
              <rect
                x={x0}
                y={y0}
                width="200"
                height={Math.max(...pumps.map((n) => n.py)) - y0 + 75}
                rx="10"
                fill="var(--surface-subtle)"
                stroke="var(--border)"
              />
              <text x={x0 + 12} y={y0 + 18} className="hall-label">
                МАШИННЫЙ ЗАЛ
              </text>
            </a>
          )}
          {graph.edges.map((edge, i) => {
            return (
              <g
                key={`${edge.from}-${edge.to}-${i}`}
                data-from={edge.from}
                data-to={edge.to}
              >
                <path
                  d={edge.path}
                  fill="none"
                  stroke={edge.kind === "throttle" ? "var(--chart-status-warning)" : "var(--chart-ink)"}
                  strokeWidth={3}
                  strokeDasharray={edge.kind === "throttle" ? "7 4" : undefined}
                  markerEnd="url(#ppd-flow)"
                />
              </g>
            );
          })}
          {[...graph.nodes]
            .sort(
              (a, b) =>
                Number(a.type !== "reservoir") - Number(b.type !== "reservoir"),
            )
            .map((node) => {
              const chosenPump = node.type === "pump" && node.agg === aggregate;
              const tone = chosenPump && audit?.quality.status !== "unfit"
                ? audit?.pump_assessment.tone
                : undefined;
              const fill = ({ok: "var(--chart-status-success-soft)", warn: "var(--chart-status-warning-soft)", bad: "var(--chart-status-danger-soft)"} as Record<string,string>)[tone ?? ""] ?? "var(--chart-surface)";
              let symbol = [
                "source",
                "prep",
                "meter",
                "pump",
                "valve",
                "wells",
                "reservoir",
              ].includes(node.type)
                ? node.type
                : "manifold";
              if (
                node.type === "manifold" &&
                node.label?.toLowerCase().includes("выкид")
              )
                symbol = "meter";
              if (
                node.type === "prep" &&
                node.label?.toLowerCase().includes("ёмк")
              )
                symbol = "source";
              const labelY =
                node.type === "wells"
                  ? -45
                  : node.type === "reservoir"
                    ? 8
                    : 55;
              return (
                <g
                  key={node.id}
                  role="img"
                  aria-label={node.type === "wells" ? `Группа нагнетательных скважин${wellCount ? `: ${wellCount}` : ""}` : node.label || node.id}
                  data-node={node.id}
                  className="equipment-node"
                  transform={`translate(${node.px} ${node.py})`}
                  style={
                    {
                      color: chosenPump ? "var(--chart-primary)" : "var(--chart-ink)",
                      "--pump-fill": fill,
                    } as CSSProperties
                  }
                >
                  <title>
                    {[node.label, node.sub, node.hint]
                      .filter(Boolean)
                      .join("\n")}
                  </title>
                  <use href={`#ppd-${symbol}`} />
                  <rect
                    className="node-hit"
                    x="-82"
                    y="-35"
                    width="164"
                    height="72"
                    rx="8"
                    fill="transparent"
                    stroke={chosenPump ? "var(--chart-status-warning)" : "transparent"}
                    strokeWidth="2"
                  />
                  <text y={labelY} className="node-label">
                    {node.type === "wells" ? "Группа скважин" : node.label?.replaceAll("\n", " ") || node.id}
                  </text>
                  {node.type === "wells" && wellCount && <text y={labelY + 17} className="node-sub well-group-count">В расчёте: {wellCount} скважин</text>}
                  {node.sub && node.type !== "wells" && (
                    <text y={labelY + 17} className="node-sub">
                      {node.sub.replaceAll("\n", " ")}
                    </text>
                  )}
                </g>
              );
            })}
        </g>
      </svg>
    </div>
  );
}
