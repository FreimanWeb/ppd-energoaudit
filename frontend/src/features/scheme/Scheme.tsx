import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import symbols from "../../../../shared/ppd-symbols.svg?raw";
import { layoutTopology, pressureForEdge } from "./scheme.mjs";
import type { Audit, Equipment, Topology } from "../../shared/types";
import { fmt } from "../../shared/ui/format";

export function Scheme({
  topology,
  aggregate,
  audit,
  pressures,
  selected,
  onSelect,
}: {
  topology: Topology;
  aggregate: string;
  audit?: Audit;
  pressures?: Record<string, {p_in_mpa: number; p_out_mpa: number}>;
  selected: string;
  onSelect: (node: Equipment) => void;
}) {
  const stage = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const [callout, setCallout] = useState<{ left: number; top: number; x: number; y: number; connectorY: number; below: boolean } | null>(null);
  const graph = layoutTopology(topology);
  const activePump = graph.nodes.find(node => node.type === "pump" && node.agg === aggregate);
  useLayoutEffect(() => {
    if (!activePump || !audit || !stage.current || !svg.current || !card.current) return;
    const place = () => {
      const matrix = svg.current?.getScreenCTM();
      const bounds = stage.current?.getBoundingClientRect();
      if (!matrix || !bounds || !card.current) return;
      const outlet = graph.edges.find(edge => edge.source.id === activePump.id)?.target;
      const lowerBranch = outlet != null && activePump.py > outlet.py;
      const point = new DOMPoint(activePump.px + 72, activePump.py + (lowerBranch ? 20 : -20)).matrixTransform(matrix);
      const x = point.x - bounds.left, y = point.y - bounds.top;
      const bendX = Math.max(activePump.px + 72, ...graph.edges.filter(edge => edge.source.id === activePump.id).map(edge => edge.middle));
      const bend = new DOMPoint(bendX, activePump.py).matrixTransform(matrix);
      const left = Math.max(12, Math.min(Math.max(x + 36, bend.x - bounds.left + 12), bounds.width - card.current.offsetWidth - 12));
      const height = card.current.offsetHeight;
      const preferredTop = lowerBranch ? y + 12 : y - height + 12;
      const top = Math.max(12, Math.min(preferredTop, svg.current!.getBoundingClientRect().height - height - 12));
      const connectorY = Math.max(top + 12, Math.min(y, top + height - 12));
      const below = bounds.width < 700 || [...svg.current!.querySelectorAll(".equipment-node use")].some(node => {
        const box = node.getBoundingClientRect();
        return bounds.left + left < box.right && bounds.left + left + card.current!.offsetWidth > box.left
          && bounds.top + top < box.bottom && bounds.top + top + height > box.top;
      });
      setCallout({ left, top, x, y, connectorY, below });
    };
    const observer = new ResizeObserver(place);
    observer.observe(svg.current);
    observer.observe(card.current);
    place();
    return () => observer.disconnect();
  }, [topology, aggregate, audit]);
  const pumps = graph.nodes.filter((n) => n.type === "pump");
  const x0 = Math.min(...pumps.map((n) => n.px)) - 100;
  const y0 = Math.min(...pumps.map((n) => n.py)) - 70;
  return (
    <div className="scheme-stage" ref={stage}>
      <svg
        ref={svg}
        className="equipment-scheme"
        viewBox={`0 0 ${graph.width} ${graph.height}`}
        aria-label="Технологическая схема ППД"
      >
        <title>Оборудование, водоводы, скважины и пласт</title>
        <g dangerouslySetInnerHTML={{ __html: symbols }} />
        <g>
          {pumps.length > 0 && (
            <g>
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
            </g>
          )}
          {graph.edges.map((edge, i) => {
            const pressure = pressureForEdge(
              edge,
              aggregate,
              audit?.snapshot ?? null,
              pressures,
            );
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
                  strokeWidth="3"
                  strokeDasharray={edge.kind === "throttle" ? "7 4" : undefined}
                  markerEnd="url(#ppd-flow)"
                />
                {pressure !== null && (
                  <text
                    x={edge.middle}
                    y={
                      (edge.target.type === "pump"
                        ? edge.target.py
                        : edge.source.py) - 40
                    }
                    className="pressure-label"
                  >
                    {edge.target.type === "pump" ? "pвх" : "pвых"} ={" "}
                    {fmt(pressure, 2)} МПа
                  </text>
                )}
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
                  role="button"
                  tabIndex={0}
                  aria-label={node.label || node.id}
                  aria-pressed={selected === node.id}
                  data-node={node.id}
                  className="equipment-node"
                  transform={`translate(${node.px} ${node.py})`}
                  style={
                    {
                      color: chosenPump ? "var(--chart-primary)" : "var(--chart-ink)",
                      "--pump-fill": fill,
                    } as CSSProperties
                  }
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={() => onSelect(node)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(node);
                    }
                  }}
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
                    stroke={selected === node.id ? "var(--chart-status-warning)" : "transparent"}
                    strokeWidth="2"
                  />
                  <text y={labelY} className="node-label">
                    {node.label?.replaceAll("\n", " ") || node.id}
                  </text>
                  {node.sub && (
                    <text y={labelY + 17} className="node-sub">
                      {node.sub.replaceAll("\n", " ")}
                    </text>
                  )}
                </g>
              );
            })}
        </g>
      </svg>
      {activePump && audit && <>
        {callout && !callout.below && <svg className="pump-regime-leader" aria-hidden="true">
          <path d={`M ${callout.left} ${callout.connectorY} L ${callout.x} ${callout.y}`} />
          <circle cx={callout.x} cy={callout.y} r="3" />
        </svg>}
        <div className={`pump-regime-card${callout?.below ? " is-below" : ""}`} ref={card} role="group" aria-label="Режим выбранного агрегата" style={{ left: callout?.left ?? 12, top: callout?.top ?? 12 }}>
          <h3>{aggregate} · параметры режима</h3>
          <dl>
            {[
              { label: "Напор", value: audit.audit.metrics.h_fact_m, unit: "м" },
              { label: "Подача", value: audit.audit.metrics.flow_m3h, unit: "м³/ч" },
              { label: "Электрическая мощность", value: audit.audit.metrics.p_electric_kw, unit: "кВт" },
              { label: "Гидравлическая мощность", value: audit.audit.metrics.p_hydraulic_kw, unit: "кВт" },
            ].map(item => <div key={item.label}>
              <dt>{item.label}</dt>
              <dd><strong>{fmt(item.value, 1)}</strong><span>{item.unit}</span></dd>
            </div>)}
          </dl>
        </div>
      </>}
    </div>
  );
}
