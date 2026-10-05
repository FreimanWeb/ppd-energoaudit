import { useRef, useState, type CSSProperties, type PointerEvent } from "react";
import symbols from "../../shared/ppd-symbols.svg?raw";
import { layoutTopology, pressureForEdge } from "./scheme.mjs";
import type { Audit, Equipment, Topology } from "./types";

export function Scheme({
  topology,
  aggregate,
  audit,
  selected,
  onSelect,
}: {
  topology: Topology;
  aggregate: string;
  audit?: Audit;
  selected: string;
  onSelect: (node: Equipment) => void;
}) {
  const graph = layoutTopology(topology);
  const [view, setView] = useState({ zoom: 1, x: 0, y: 0 });
  const drag = useRef<{
    x: number;
    y: number;
    startX: number;
    startY: number;
  } | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const pumps = graph.nodes.filter((n) => n.type === "pump");
  const x0 = Math.min(...pumps.map((n) => n.px)) - 100;
  const y0 = Math.min(...pumps.map((n) => n.py)) - 70;
  function move(event: PointerEvent<SVGSVGElement>) {
    if (!drag.current || !svg.current) return;
    const box = svg.current.getBoundingClientRect();
    const scale = Math.max(graph.width / box.width, graph.height / box.height);
    setView((v) => ({
      ...v,
      x: drag.current!.startX + (event.clientX - drag.current!.x) * scale,
      y: drag.current!.startY + (event.clientY - drag.current!.y) * scale,
    }));
  }
  return (
    <>
      <div className="scheme-tools">
        <span>Выберите оборудование на схеме</span>
        <div>
          <button
            aria-label="Уменьшить схему"
            onClick={() =>
              setView((v) => ({ ...v, zoom: Math.max(0.5, v.zoom / 1.2) }))
            }
          >
            −
          </button>
          <span>{Math.round(view.zoom * 100)}%</span>
          <button
            aria-label="Увеличить схему"
            onClick={() =>
              setView((v) => ({ ...v, zoom: Math.min(3, v.zoom * 1.2) }))
            }
          >
            +
          </button>
          <button onClick={() => setView({ zoom: 1, x: 0, y: 0 })}>
            По размеру
          </button>
        </div>
      </div>
      <svg
        ref={svg}
        className="equipment-scheme"
        viewBox={`0 0 ${graph.width} ${graph.height}`}
        aria-label="Технологическая схема ППД"
        onPointerDown={(e) => {
          if (e.button !== 0) return;
          e.currentTarget.setPointerCapture(e.pointerId);
          drag.current = {
            x: e.clientX,
            y: e.clientY,
            startX: view.x,
            startY: view.y,
          };
        }}
        onPointerMove={move}
        onPointerUp={() => {
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
      >
        <title>Оборудование, водоводы, скважины и пласт</title>
        <g dangerouslySetInnerHTML={{ __html: symbols }} />
        <g
          transform={`translate(${view.x} ${view.y}) translate(${graph.width / 2} ${graph.height / 2}) scale(${view.zoom}) translate(${-graph.width / 2} ${-graph.height / 2})`}
        >
          {pumps.length > 0 && (
            <g>
              <rect
                x={x0}
                y={y0}
                width="200"
                height={Math.max(...pumps.map((n) => n.py)) - y0 + 75}
                rx="10"
                fill="#edf4f1"
                stroke="#d8e3df"
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
                  stroke={edge.kind === "throttle" ? "#c58b25" : "#4a5d57"}
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
                    {pressure.toFixed(2)} МПа
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
              const metrics =
                chosenPump && audit?.quality.status !== "unfit"
                  ? audit?.audit.metrics
                  : undefined;
              const ratio =
                metrics?.eta_unit && metrics.eta_nom
                  ? metrics.eta_unit / metrics.eta_nom
                  : null;
              const fill =
                ratio === null
                  ? "white"
                  : ratio >= 0.9
                    ? "#cfe8dc"
                    : ratio >= 0.78
                      ? "#f6e3b4"
                      : "#f2cecb";
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
                      color: chosenPump ? "#1f4e4a" : "#4a5d57",
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
                    stroke={selected === node.id ? "#c58b25" : "transparent"}
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
      <div className="legend">
        <span>
          <i className="dot good" />
          КПД близок к номинальному
        </span>
        <span>
          <i className="dot warn" />
          КПД снижен
        </span>
        <span>
          <i className="dot bad" />
          КПД значительно снижен
        </span>
        <span>Цвет относится только к выбранному агрегату</span>
      </div>
    </>
  );
}
