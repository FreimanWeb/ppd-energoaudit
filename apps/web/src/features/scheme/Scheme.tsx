import {Text} from "@visx/text";
import {lossLabels} from "../../shared/lossLabels";
import { type CSSProperties } from "react";
import type {OperatorBalance} from "./LossFlow";
import {fmt} from "../../shared/ui/format";
import symbols from "../../../../../shared/ppd-symbols.svg?raw";
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
  balance,
  textScale=1,
}: {
  topology: Topology;
  aggregate: string;
  audit?: Audit;
  pressures?: Record<string, {p_in_mpa: number; p_out_mpa: number}>;
  activeStage?:string|null;
  onStageHover?:(id:string|null)=>void;
  onStageFocus?:(id:string|null)=>void;
  wellCount?: number;
  balance?: OperatorBalance|null;
  textScale?: number;
}) {
  const interaction = (id:string) => ({
    "data-stage":id,"data-active":activeStage===id?true:undefined,
    onPointerEnter:()=>onStageHover?.(id),onPointerLeave:()=>onStageHover?.(null),
    onFocus:()=>onStageFocus?.(id),onBlur:()=>onStageFocus?.(null),
  });
  const graph = layoutTopology(topology);
  const pipeEdge = graph.edges.find(edge => edge.source.type === "manifold" && edge.target.type === "valve");
  const wells = graph.nodes.find(node => node.type === "wells");
  const choke=graph.nodes.find(node=>node.type === "choke");
  const wellAreaLeft=wells ? wells.px-40 : 0;
  const pumps = graph.nodes.filter((n) => n.type === "pump");
  const x0 = Math.min(...pumps.map((n) => n.px)) - 100;
  const y0 = Math.min(...pumps.map((n) => n.py)) - 70;
  const manifold=pipeEdge?.source;
  const pumpOutlet=graph.edges.find(edge=>edge.source.type === "pump" && edge.target.id === manifold?.id);
  const lossAnchors=[
    ...(pumps.length ? [
      {id:"nominal",stage:"hall",x:x0+28,y:Math.max(...pumps.map(node=>node.py))},
      {id:"efficiency",stage:"hall",x:x0+172,y:Math.max(...pumps.map(node=>node.py))},
    ] : []),
    ...(pumpOutlet ? [{id:"pump_bg",stage:"hall",x:pumpOutlet.middle+(pumpOutlet.target.px-40-pumpOutlet.middle)/4,y:pumpOutlet.target.py}] : []),
    ...(pipeEdge ? [{id:"friction",stage:"pipes",x:(pipeEdge.source.px+pipeEdge.target.px)/2,y:pipeEdge.source.py},
      {id:"local",stage:"pipes",x:pipeEdge.target.px,y:pipeEdge.target.py}] : []),
    ...(choke ? [{id:"choke",stage:"pipes",x:choke.px,y:choke.py}] : []),
  ];
  const powerReadings=[
    ...(pumps.length ? [{id:"input",label:lossLabels.input,description:"Потреблённая электрическая мощность",x:x0-30,anchorX:x0,anchorY:y0+40,bendX:x0-30,power:balance?.input_kw}] : []),
    ...(manifold ? [{id:"bg",label:lossLabels.bg,description:"Гидравлическая мощность на БГ — промежуточный итог",x:manifold.px,anchorX:manifold.px,anchorY:manifold.py-38,power:balance?.bg_kw}] : []),
    ...(wells ? [{id:"output",label:lossLabels.output,description:"Гидравлическая мощность на устьях после штуцеров",x:wells.px+110,anchorX:wells.px+18,anchorY:wells.py,bendX:wells.px+110,power:balance?.output_kw}] : []),
  ];
  return (
    <div className="scheme-stage" style={{"--scheme-text-scale":textScale} as CSSProperties}>
      <svg
        className="equipment-scheme"
        viewBox={`-40 -125 ${graph.width} ${graph.height+125}`}
        aria-label="Условная технологическая схема ППД"
      >
        <title>Оборудование, водоводы, скважины и пласт</title>
        <g dangerouslySetInnerHTML={{ __html: symbols }} />
        <g>
          {pipeEdge && <a href="#pipelines" aria-label="Открыть трубопроводы" className="scheme-area-link" {...interaction("pipes")}>
            <rect x={pipeEdge.source.px + 56} y={pipeEdge.source.py - 50} width={Math.max(40,(choke?.px ?? pipeEdge.target.px) - pipeEdge.source.px - 6)} height="100" rx="10" fill="var(--surface-subtle)" stroke="var(--border)" />
          </a>}
          {wells && <a href="#wells" aria-label="Открыть скважины" className="scheme-area-link" {...interaction("wells")}>
            <rect x={wellAreaLeft} y={wells.py - 60} width={wells.px+90-wellAreaLeft} height="250" rx="10" fill="var(--surface-subtle)" stroke="var(--border)" />
          </a>}
          {pumps.length > 0 && (
            <a href="#machine-block" aria-label="Открыть машинный блок" className="scheme-area-link" {...interaction("hall")}>
              <rect
                x={x0}
                y={y0}
                width="200"
                height={Math.max(...pumps.map((n) => n.py)) - y0 + Math.max(87,55+24*textScale)}
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
                  stroke="var(--chart-ink)"
                  strokeWidth={3}
                  strokeDasharray={edge.target.type === "choke" ? "7 4" : undefined}
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
              const isChoke=node.id === choke?.id;
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
                "choke",
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
              if(isChoke) symbol="choke";
              const labelY =
                node.type === "wells"
                  ? -45
                  : node.type === "reservoir"
                    ? 8
                    : node.type === "valve" || isChoke ? 41 : 55;
              return (
                <g
                  key={node.id}
                  role="img"
                  aria-label={node.type === "wells" ? `Группа нагнетательных скважин${wellCount ? `: ${wellCount}` : ""}` : isChoke ? "Штуцеры нагнетательных скважин" : node.label || node.id}
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
                    {[isChoke ? "Штуцеры нагнетательных скважин" : node.label, node.sub, node.hint]
                      .filter(Boolean)
                      .join("\n")}
                  </title>
                  <use href={`#ppd-${symbol}`} transform={node.type === "reservoir" ? "translate(-68 0) scale(0.7 1)" : undefined} />
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
                  <text x={node.type === "reservoir" ? -80 : undefined} y={labelY} className="node-label">
                    {node.type === "wells" ? `Группа скважин${wellCount ? ` (${wellCount} шт.)` : ""}` : isChoke ? "Штуцеры" : node.label?.replaceAll("\n", " ") || node.id}
                  </text>
                  {node.sub && node.type !== "wells" && (
                    <text y={labelY + 20*textScale} className="node-sub">
                      {node.sub.replaceAll("\n", " ")}
                    </text>
                  )}
                </g>
              );
            })}
          {powerReadings.map(reading=>{
            const known=typeof reading.power === "number" && Number.isFinite(reading.power);
            const value=known ? `${fmt(reading.power,1)} кВт` : "Нет данных";
            const share=known && balance && balance.input_kw>0 ? `${fmt(reading.power!/balance.input_kw*100,1)} % ввода` : "";
            return <g key={reading.id} className="scheme-power-reading" data-reading={reading.id} data-power={known ? reading.power : undefined} role="img" aria-label={`${reading.description}: ${value}${share ? ` · ${share}` : ""}`} transform={`translate(${reading.x} -65)`}>
              <title>{reading.description}</title>
              <path className="scheme-power-leader" d={`M 0 ${54*textScale} H ${(reading.bendX ?? reading.anchorX)-reading.x} V ${reading.anchorY+65} H ${reading.anchorX-reading.x}`}/>
              <circle className="scheme-power-anchor" cx={reading.anchorX-reading.x} cy={reading.anchorY+65} r="3"/>
              <Text textAnchor="middle" verticalAnchor="end" dy={-4*textScale} width={230} lineHeight={`${14*textScale}px`} fontSize={12*textScale} className="scheme-power-label">{reading.label}</Text>
              <text y={20*textScale} textAnchor="middle" className="scheme-power-value">{value}</text>
              {share && <text y={40*textScale} textAnchor="middle" className="scheme-power-share">{share}</text>}
            </g>;
          })}
          {lossAnchors.map(anchor=><circle key={anchor.id} className="scheme-loss-anchor" data-loss={anchor.id} data-stage={anchor.stage}
            data-active={activeStage === anchor.stage ? true : undefined} cx={anchor.x} cy={anchor.y} r="3"/>) }
        </g>
      </svg>
    </div>
  );
}
