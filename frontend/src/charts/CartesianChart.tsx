import {
  memo,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { AxisBottom, AxisLeft, type AxisScale } from "@visx/axis";
import { ParentSize } from "@visx/responsive";
import { scaleBand, scaleLinear, scaleTime } from "@visx/scale";
import { LinePath, Area, Bar } from "@visx/shape";
import { curveLinear, curveStepAfter } from "@visx/curve";
import { Brush, type BrushProps } from "@visx/brush";
import type {
  CartesianModel,
  AxisModel,
  SeriesModel,
  PointModel,
  TimeInteraction,
} from "./types";
import {
  barIntervals,
  chartDomains,
  viewPoints,
} from "./cartesianGeometry.mjs";
import { chartTheme } from "./theme";
import { Tooltip as ExplanationTooltip } from "../shared/ui/Tooltip";
import { ChartTooltip, type ChartTooltipRow } from "./ChartTooltip";
import "./charts.css";

const number = (value: unknown) =>
  typeof value === "number"
    ? new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 }).format(value)
    : String(value ?? "—");
function axisTick(value: unknown, type: string) {
  if (type === "time")
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(Number(value)));
  const text = number(value);
  return type === "category" && text.length > 18
    ? `${text.slice(0, 16)}…`
    : text;
}
function makeScale(
  axis: AxisModel,
  domain: (string | number)[],
  range: [number, number],
  viewport: boolean,
): AxisScale {
  const output: [number, number] = axis.reversed ? [range[1], range[0]] : range;
  if (axis.type === "category")
    return scaleBand<string>({
      domain: domain.map(String),
      range: output,
      padding: 0.3,
    });
  const numeric = domain as [number, number];
  if (axis.type === "time")
    return scaleTime({
      domain: numeric.map((v) => new Date(v)),
      range: output,
      nice: !viewport && !axis.domain,
    });
  return scaleLinear({
    domain: numeric,
    range: output,
    nice: !viewport && !axis.domain,
  });
}
function coordinate(
  scale: AxisScale,
  axis: AxisModel,
  value: number | string,
): number {
  if (axis.type === "category") {
    const band = scale as ReturnType<typeof scaleBand<string>>;
    return Number(band(String(value))) + band.bandwidth() / 2;
  }
  return Number(scale(Number(value)));
}
type BarInterval = {
  series: Pick<SeriesModel, "id" | "name" | "color">;
  point: PointModel;
  start: number;
  end: number;
  value: number;
  index: number;
  seriesIndex: number;
  count: number;
};
type Tip = {
  title: string;
  rows: ChartTooltipRow[];
  x: number;
  y: number;
};
const CurveSeries = memo(function CurveSeries({
  series,
  points,
  xScale,
  yScale,
  model,
}: {
  series: SeriesModel;
  points: PointModel[];
  xScale: AxisScale;
  yScale: AxisScale;
  model: CartesianModel;
}) {
  const x = (point: PointModel) => coordinate(xScale, model.xAxis, point.x);
  const y = (point: PointModel) =>
    coordinate(yScale, model.yAxis, point.y as number);
  const curve = series.curve === "stepAfter" ? curveStepAfter : curveLinear;
  if (series.type === "band")
    return (
      <Area
        className="visx-band"
        data={points}
        x={x}
        y0={(p) => coordinate(yScale, model.yAxis, p.low as number)}
        y1={(p) => coordinate(yScale, model.yAxis, p.high as number)}
        defined={(p) => p.low != null && p.high != null}
        fill={series.fill ?? series.color}
        fillOpacity={0.16}
        stroke="none"
        curve={curve}
      />
    );
  const data = series.connectNulls ? points.filter((p) => p.y != null) : points;
  return (
    <g>
      <LinePath
        className="visx-line"
        {...{ name: series.name }}
        data-series={series.id}
        data={data}
        x={x}
        y={y}
        defined={(p) => p.y != null && Number.isFinite(p.y)}
        curve={curve}
        fill="none"
        stroke={series.color}
        strokeWidth={series.width}
        strokeDasharray={series.dashed ? "5 5" : undefined}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {series.markers &&
        points.length <= 300 &&
        points.map((p, i) =>
          p.y != null ? (
            <circle
              key={i}
              cx={x(p)}
              cy={y(p)}
              r={3}
              fill={p.color ?? series.color}
              stroke="white"
              strokeWidth={1.5}
            />
          ) : null,
        )}
    </g>
  );
});

export function CartesianPlot({
  model,
  width,
  height = model.height,
  hidden = [],
  viewport = null,
  onViewport,
  onSelect,
  timeInteraction,
}: {
  model: CartesianModel;
  width: number;
  height?: number;
  hidden?: string[];
  viewport?: [number, number] | null;
  onViewport?: (value: [number, number] | null) => void;
  onSelect?: (id: string) => void;
  timeInteraction?: TimeInteraction;
}) {
  const id = useId().replace(/:/g, "");
  const brushRef = useRef<NonNullable<BrushProps["innerRef"]>["current"]>(null);
  const [tip, setTip] = useState<Tip | null>(null);
  const [activeBar, setActiveBar] = useState<string | null>(null);
  const hasBrush = model.xAxis.type === "time" && model.data.length > 2 && timeInteraction?.showBrush !== false;
  const left = model.yAxis.hidden ? 12 : model.horizontal ? 110 : 66,
    right = 20,
    top = 24,
    bottom = model.xAxis.hidden ? 12 : 48;
  const innerWidth = Math.max(10, width - left - right),
    innerHeight = Math.max(30, height - top - bottom - (hasBrush ? 56 : 0));
  useEffect(() => {
    if (viewport === null && brushRef.current) brushRef.current.updateBrush((state) => ({
      ...state, start: { x: 0, y: 0 }, end: { x: innerWidth, y: 16 },
      extent: { x0: 0, x1: innerWidth, y0: 0, y1: 16 },
    }));
  }, [viewport === null, innerWidth]);
  const projection = useMemo(() => {
    const visible = model.series.filter((s) => !hidden.includes(s.id));
    const domains = chartDomains(model, hidden, viewport);
    if (timeInteraction && !viewport) domains.x = timeInteraction.domain;
    const xScale = makeScale(
      model.xAxis,
      domains.x,
      [0, innerWidth],
      Boolean(viewport),
    );
    const yScale = makeScale(
      model.yAxis,
      domains.y,
      model.yAxis.type === "category" ? [0, innerHeight] : [innerHeight, 0],
      false,
    );
    const series = visible.map((s) => ({
      series: s,
      points: viewPoints(s.points, viewport) as PointModel[],
    }));
    const xs = [...new Set(visible.flatMap((s) => s.points.map((p) => p.x)))];
    if (model.xAxis.type !== "category")
      xs.sort((a, b) => Number(a) - Number(b));
    const pointMaps = visible.map(
      (s) => new Map(s.points.map((p) => [p.x, p])),
    );
    return {
      xScale,
      yScale,
      series,
      xs,
      pointMaps,
      bars: barIntervals(model, hidden, viewport) as BarInterval[],
      domains,
    };
  }, [model, hidden, viewport, innerWidth, innerHeight, timeInteraction?.domain]);
  const { xScale, yScale, series, xs, pointMaps, bars } = projection;
  const x = (value: number | string) => coordinate(xScale, model.xAxis, value),
    y = (value: number | string) => coordinate(yScale, model.yAxis, value);
  const barOnly =
    model.variant === "waterfall" ||
    model.series.every((s) => s.type === "bar");
  const axisLabel = model.horizontal ? model.xAxis.label : model.yAxis.label;
  const unit = axisLabel.includes(",") ? axisLabel.split(",").at(-1)?.trim() : axisLabel;
  function showIndex(index: number, py = innerHeight / 2) {
    const value = xs[index];
    if (value === undefined) return;
    const points = pointMaps.map((map) => map.get(value));
    const rows = series.flatMap(({ series: s }, i) => {
      const p = points[i];
      if (!p || p.y == null) return [];
      return [
        {
          name: s.name,
          value:
            s.type === "band" && p.low != null && p.high != null
              ? ([p.low, p.high] as [number, number])
              : p.y,
          color: p.color ?? s.color,
          unit,
        },
      ];
    });
    const title = points.find(Boolean)?.label ?? number(value);
    setTip({ title, rows, x: left + x(value), y: top + py });
    setActiveBar(null);
    timeInteraction?.onCursor(Number(value));
  }
  useEffect(() => {
    if (!timeInteraction) return;
    const value = timeInteraction.cursor;
    if (value == null || x(value) < 0 || x(value) > innerWidth) { setTip(null); return; }
    const rows = series.flatMap(({ series: s }) => {
      const point = s.points.find((p) => Number(p.x) === value);
      return point?.y != null ? [{ name: s.name, value: point.y, color: s.color, unit }] : [];
    });
    setTip({ title: new Date(value).toLocaleString("ru-RU"), rows, x: left + x(value), y: top + innerHeight / 2 });
  }, [timeInteraction?.cursor, viewport, model, width, hidden]);
  function pointer(event: React.PointerEvent<SVGSVGElement>) {
    if (barOnly || (event.target as Element).closest(".visx-bar")) return;
    const bounds = event.currentTarget.getBoundingClientRect(),
      px = event.clientX - bounds.left - left,
      py = event.clientY - bounds.top - top;
    if (px < 0 || px > innerWidth || py < 0 || py > innerHeight) {
      setTip(null);
      timeInteraction?.onCursor(null);
      return;
    }
    let index = 0;
    if (model.xAxis.type === "category") {
      let distance = Infinity;
      xs.forEach((v, i) => {
        const d = Math.abs(x(v) - px);
        if (d < distance) {
          distance = d;
          index = i;
        }
      });
    } else {
      const target = Number("invert" in xScale ? xScale.invert(px) : 0);
      let lo = 0,
        hi = xs.length;
      while (lo < hi) {
        const mid = (lo + hi) >>> 1;
        if (Number(xs[mid]) < target) lo = mid + 1;
        else hi = mid;
      }
      index = Math.min(lo, xs.length - 1);
      if (
        index > 0 &&
        Math.abs(Number(xs[index - 1]) - target) <
          Math.abs(Number(xs[index]) - target)
      )
        index--;
    }
    showIndex(index, py);
  }
  const brushDomain = (timeInteraction?.domain ?? chartDomains(model, hidden).x) as [number, number];
  const visiblePeriod = viewport ?? brushDomain;
  function moveBoundary(event: React.KeyboardEvent<SVGGElement>, leftBoundary: boolean) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    brushRef.current?.updateBrush(state => {
      const min = leftBoundary ? 0 : state.extent.x0 + 1;
      const max = leftBoundary ? state.extent.x1 - 1 : innerWidth;
      const current = leftBoundary ? state.extent.x0 : state.extent.x1;
      const target = event.key === "Home" ? min : event.key === "End" ? max : current + (event.key === "ArrowRight" ? 1 : -1) * innerWidth / 100;
      const value = Math.max(min, Math.min(max, target));
      const x0 = leftBoundary ? value : state.extent.x0, x1 = leftBoundary ? state.extent.x1 : value;
      return { ...state, start: { x: x0, y: 0 }, end: { x: x1, y: 16 }, extent: { x0, x1, y0: 0, y1: 16 } };
    });
  }
  const periodLabel = (value: number) => innerWidth < 360
    ? new Date(value).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" })
    : axisTick(value, "time");
  const gridScale = model.horizontal ? xScale : yScale;
  const ticks = "ticks" in gridScale ? gridScale.ticks(4) : [];
  const categoryScale = model.horizontal ? yScale : xScale;
  const barSpan =
    ("bandwidth" in categoryScale
      ? categoryScale.bandwidth()
      : (model.horizontal ? innerHeight : innerWidth) /
        Math.max(1, new Set(bars.map((bar) => bar.point.x)).size)) * 0.78;
  return (
    <div
      className="native-chart-surface"
      style={{ position: "relative", width, height }}
    >
      <svg
        className="visx-chart"
        width={width}
        height={height}
        role="img"
        aria-label={model.title}
        data-time-domain={projection.domains.x.join(",")}
        onClick={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const px = event.clientX - bounds.left - left, py = event.clientY - bounds.top - top;
          if (!(event.target as Element).closest(".visx-brush") && px >= 0 && px <= innerWidth && py >= 0 && py <= innerHeight && timeInteraction?.cursor != null)
            timeInteraction.onSelectX?.(timeInteraction.cursor);
        }}
        tabIndex={barOnly ? -1 : 0}
        onPointerMove={pointer}
        onPointerLeave={() => {
          setTip(null);
          setActiveBar(null);
          timeInteraction?.onCursor(null);
        }}
        onKeyDown={(event) => {
          if ((event.target as Element).closest(".visx-bar")) return;
          if (event.key === "Escape") {
            setTip(null);
            timeInteraction?.onCursor(null);
            return;
          }
          if (event.key === "Enter" && timeInteraction?.cursor != null) {
            event.preventDefault();
            timeInteraction.onSelectX?.(timeInteraction.cursor);
            return;
          }
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
            return;
          event.preventDefault();
          const previous = xs.findIndex((v) => timeInteraction
            ? Number(v) === timeInteraction.cursor
            : pointMaps.some((map) => map.get(v)?.label === tip?.title));
          const next =
            event.key === "Home"
              ? 0
              : event.key === "End"
                ? xs.length - 1
                : Math.max(
                    0,
                    Math.min(
                      xs.length - 1,
                      previous + (event.key === "ArrowLeft" ? -1 : 1),
                    ),
                  );
          showIndex(next);
        }}
      >
        <title>{model.title}</title>
        <defs>
          <clipPath id={`clip-${id}`}>
            <rect width={innerWidth} height={innerHeight} />
          </clipPath>
        </defs>
        <g transform={`translate(${left},${top})`}>
          <g aria-hidden="true">
            {ticks.map((value, i) =>
              model.horizontal ? (
                <line
                  key={i}
                  x1={x(Number(value))}
                  x2={x(Number(value))}
                  y1={0}
                  y2={innerHeight}
                  stroke={chartTheme.grid}
                  strokeDasharray="4 4"
                />
              ) : (
                <line
                  key={i}
                  x1={0}
                  x2={innerWidth}
                  y1={y(Number(value))}
                  y2={y(Number(value))}
                  stroke={chartTheme.grid}
                  strokeDasharray="4 4"
                />
              ),
            )}
          </g>
          <g clipPath={`url(#clip-${id})`}>
            {timeInteraction?.cursor != null && <line className="visx-crosshair" data-timestamp={timeInteraction.cursor} x1={x(timeInteraction.cursor)} x2={x(timeInteraction.cursor)} y1={0} y2={innerHeight} stroke={chartTheme.text} strokeDasharray="3 3" pointerEvents="none" />}
            {series
              .filter(({ series: s }) => s.type === "line" || s.type === "band")
              .map(({ series: s, points }) => (
                <CurveSeries
                  key={s.id}
                  series={s}
                  points={points}
                  xScale={xScale}
                  yScale={yScale}
                  model={model}
                />
              ))}
            {bars.map((bar, index) => {
              const count = model.stacked ? 1 : bar.count,
                span = Math.min(48, Math.max(1, barSpan / count - 3)),
                offset = model.stacked
                  ? 0
                  : bar.seriesIndex * (span + 3) -
                    ((count - 1) * (span + 3)) / 2;
              const bx = model.horizontal
                ? Math.min(x(bar.start), x(bar.end))
                : x(bar.point.x) - span / 2 + offset;
              const by = model.horizontal
                ? y(bar.point.x) - span / 2 + offset
                : Math.min(y(bar.start), y(bar.end));
              const bw = model.horizontal
                  ? Math.abs(x(bar.end) - x(bar.start))
                  : span,
                bh = model.horizontal
                  ? span
                  : Math.abs(y(bar.end) - y(bar.start));
              const key = `${bar.series.id}-${index}`;
              const show = () => {
                setActiveBar(key);
                setTip({
                  title: bar.point.label || bar.series.name,
                  rows: [
                    {
                      name: bar.point.tooltip || model.series.length === 1 ? undefined : bar.series.name,
                      value: bar.point.tooltip?.value ?? bar.value,
                      unit: bar.point.tooltip?.unit ?? unit,
                      share: bar.point.tooltip?.share,
                      color: bar.point.color ?? bar.series.color,
                    },
                  ],
                  x: left + bx + bw / 2,
                  y: top + by,
                });
              };
              return (
                <Bar
                  key={key}
                  className={`visx-bar ${activeBar === key ? "is-active" : ""}`}
                  data-series={bar.series.id}
                  data-value={bar.value}
                  x={bx}
                  y={by}
                  width={bw}
                  height={bh}
                  rx={4}
                  fill={bar.point.color ?? bar.series.color}
                  stroke="transparent"
                  strokeWidth={1}
                  role="button"
                  tabIndex={0}
                  aria-label={`${bar.series.name}: ${number(bar.value)} ${unit}`}
                  onPointerEnter={show}
                  onPointerMove={show}
                  onPointerLeave={() => { setActiveBar(null); setTip(null); }}
                  onFocus={show}
                  onBlur={() => {
                    setActiveBar(null);
                    setTip(null);
                  }}
                  onClick={() => { const selection = bar.point.tooltip?.selection ?? bar.point.customdata; if (selection) onSelect?.(selection); }}
                  onKeyDown={(event) => {
                    const selection = bar.point.tooltip?.selection ?? bar.point.customdata;
                    if (selection && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); onSelect?.(selection); }
                    if (event.key === "Escape") {
                      setTip(null);
                      setActiveBar(null);
                    }
                  }}
                />
              );
            })}
            {series
              .filter(({ series: s }) => s.type === "scatter")
              .flatMap(({ series: s, points }) =>
                points.map((point, index) => {
                  if (point.y == null) return null;
                  const cx = x(point.x),
                    cy = y(point.y),
                    r = Math.max(3, (point.size ?? 9) / 2),
                    color = point.color ?? s.color;
                  return (
                    <g
                      key={`${s.id}-${index}`}
                      className="visx-point"
                      onPointerEnter={() =>
                        setTip({
                          title: point.label ?? number(point.x),
                          rows: [
                            { name: s.name, value: point.y as number, color, unit },
                          ],
                          x: left + cx,
                          y: top + cy,
                        })
                      }
                      onClick={() =>
                        point.customdata && onSelect?.(point.customdata)
                      }
                    >
                      {point.shape === "diamond" ? (
                        <path
                          d={`M${cx},${cy - r} L${cx + r},${cy} L${cx},${cy + r} L${cx - r},${cy} Z`}
                          fill={color}
                        />
                      ) : point.shape === "x" ? (
                        <path
                          d={`M${cx - r},${cy - r} L${cx + r},${cy + r} M${cx - r},${cy + r} L${cx + r},${cy - r}`}
                          stroke={color}
                          strokeWidth={2}
                        />
                      ) : point.shape === "square" ? (
                        <rect
                          x={cx - r}
                          y={cy - r}
                          width={r * 2}
                          height={r * 2}
                          fill={color}
                        />
                      ) : (
                        <circle cx={cx} cy={cy} r={r} fill={color} />
                      )}{" "}
                      {point.label && (
                        <text
                          x={cx}
                          y={cy - r - 6}
                          textAnchor="middle"
                          fontSize={11}
                          fill={chartTheme.text}
                        >
                          {point.label}
                        </text>
                      )}
                    </g>
                  );
                }),
              )}
            {model.references.map((ref, i) =>
              ref.axis === "x" ? (
                <g key={i} className="visx-reference">
                  <line
                    x1={x(ref.value)}
                    x2={x(ref.value)}
                    y1={0}
                    y2={innerHeight}
                    stroke={ref.color}
                    strokeDasharray={ref.dashed ? "5 5" : undefined}
                  />
                  {ref.label && (
                    <text
                      x={x(ref.value) + 5}
                      y={12}
                      fill={ref.color}
                      fontSize={11}
                    >
                      {ref.label}
                    </text>
                  )}
                </g>
              ) : (
                <g key={i} className="visx-reference">
                  <line
                    x1={0}
                    x2={innerWidth}
                    y1={y(ref.value)}
                    y2={y(ref.value)}
                    stroke={ref.color}
                    strokeDasharray={ref.dashed ? "5 5" : undefined}
                  />
                  {ref.label && (
                    <text
                      x={innerWidth - 3}
                      y={y(ref.value) - 5}
                      textAnchor="end"
                      fill={ref.color}
                      fontSize={11}
                    >
                      {ref.label}
                    </text>
                  )}
                </g>
              ),
            )}
            {model.annotations.map((a, i) => {
              const ax = a.x != null ? x(a.x) + 4 : innerWidth - 5,
                ay = a.y != null ? y(a.y) - 5 : 12;
              return (
                <text
                  key={i}
                  className="visx-annotation"
                  x={ax}
                  y={ay}
                  transform={a.vertical ? `rotate(-90,${ax},${ay})` : undefined}
                  textAnchor={
                    a.vertical ? "end" : a.x == null ? "end" : "start"
                  }
                  fill={a.color}
                  fontSize={10}
                >
                  <title>{a.text}</title>
                  {a.text}
                </text>
              );
            })}
            {tip &&
              !barOnly &&
              tip.rows.map((row, i) => {
                const source = series.find(
                  ({ series: s }) => s.name === row.name,
                );
                const point = source?.points.find((p) => p.label === tip.title);
                return point &&
                  point.y != null &&
                  source?.series.type === "line" ? (
                  <circle
                    key={i}
                    cx={x(point.x)}
                    cy={y(point.y)}
                    r={5}
                    fill={row.color}
                    stroke="white"
                    strokeWidth={2}
                  />
                ) : null;
              })}
          </g>
          {!model.xAxis.hidden && (
            <AxisBottom
              axisClassName="visx-axis-x"
              top={innerHeight}
              scale={xScale}
              hideAxisLine
              hideTicks
              numTicks={Math.max(2, Math.floor(innerWidth / 110))}
              tickFormat={(value) => axisTick(value, model.xAxis.type)}
              tickLabelProps={() => ({
                fill: chartTheme.text,
                fontSize: 11,
                textAnchor: "middle",
              })}
              label={model.xAxis.label}
              labelProps={{ fill: chartTheme.text, fontSize: 11 }}
            />
          )}
          {!model.yAxis.hidden && (
            <AxisLeft
              axisClassName="visx-axis-y"
              scale={yScale}
              hideAxisLine
              hideTicks
              numTicks={4}
              tickFormat={(value) => axisTick(value, model.yAxis.type)}
              tickLabelProps={() => ({
                fill: chartTheme.text,
                fontSize: 11,
                textAnchor: "end",
                dy: 3,
              })}
              label={model.yAxis.label}
              labelOffset={42}
              labelProps={{ fill: chartTheme.text, fontSize: 11 }}
            />
          )}
          {hasBrush && (
            <g
              className="visx-brush"
              transform={`translate(0,${innerHeight + 44})`}
              role="group"
              aria-label="Границы видимого периода"
            >
              <text className="brush-range-title" y="-12">Границы видимого периода</text>
              {innerWidth > 480 && <text className="brush-range-hint" x={innerWidth} y="-12" textAnchor="end">Перетащите левый или правый край ↔</text>}
              <rect className="brush-range-track" width={innerWidth} height="16" rx="4" />
              <text className="brush-range-date" y="32">Начало: {periodLabel(visiblePeriod[0])}</text>
              <text className="brush-range-date" x={innerWidth} y="32" textAnchor="end">Конец: {periodLabel(visiblePeriod[1])}</text>
              <Brush
                innerRef={brushRef}
                xScale={scaleLinear({
                  domain: timeInteraction?.domain ?? chartDomains(model, hidden).x as [number, number],
                  range: [0, innerWidth],
                })}
                yScale={scaleLinear({ domain: [0, 1], range: [16, 0] })}
                width={innerWidth}
                height={16}
                brushDirection="horizontal"
                handleSize={24}
                resizeTriggerAreas={["left", "right"]}
                initialBrushPosition={{
                  start: { x: 0, y: 0 },
                  end: { x: innerWidth, y: 16 },
                }}
                renderBrushHandle={({ x: handleX, width: handleWidth, height: handleHeight, className, isBrushActive }) => {
                  if (!isBrushActive) return null;
                  const leftBoundary = className.endsWith("-left");
                  return <g className={`${className} brush-boundary-handle`} transform={`translate(${handleX},0)`}
                    role="slider" tabIndex={0} aria-label={leftBoundary ? "Начало периода" : "Конец периода"}
                    aria-orientation="horizontal"
                    aria-valuemin={leftBoundary ? brushDomain[0] : visiblePeriod[0] + 1}
                    aria-valuemax={leftBoundary ? visiblePeriod[1] - 1 : brushDomain[1]}
                    aria-valuenow={visiblePeriod[leftBoundary ? 0 : 1]}
                    aria-valuetext={axisTick(visiblePeriod[leftBoundary ? 0 : 1], "time")}
                    onKeyDown={event => moveBoundary(event, leftBoundary)}>
                    <rect y="-4" width={handleWidth} height={handleHeight + 8} rx="5" />
                    <path d={`M ${handleWidth / 2 - 2} 4 V ${handleHeight - 4} M ${handleWidth / 2 + 2} 4 V ${handleHeight - 4}`} />
                  </g>;
                }}
                selectedBoxStyle={{
                  fill: chartTheme.green,
                  fillOpacity: 0.08,
                  stroke: chartTheme.green,
                  strokeOpacity: 0.4,
                }}
                onChange={(bounds) => {
                  if (bounds) {
                    const domain = timeInteraction?.domain ?? chartDomains(model, hidden).x as [number, number];
                    const range: [number, number] = [Math.max(Number(domain[0]), Number(bounds.x0)), Math.min(Number(domain[1]), Number(bounds.x1))];
                    onViewport?.(Math.abs(range[0] - Number(domain[0])) < 1 && Math.abs(range[1] - Number(domain[1])) < 1 ? null : range);
                  }
                }}
                useWindowMoveEvents
              />
            </g>
          )}
        </g>
      </svg>
      {tip && <ChartTooltip title={tip.title} rows={tip.rows} style={{
        left: Math.max(8, Math.min(width - 250, tip.x + 12)),
        top: Math.max(4, Math.min(height - 100, tip.y - 30)),
      }} />}
    </div>
  );
}

export function CartesianChart({
  model,
  onSelect,
  timeInteraction,
}: {
  model: CartesianModel;
  onSelect?: (id: string) => void;
  timeInteraction?: TimeInteraction;
}) {
  const [choices, setChoices] = useState<Record<string, boolean>>({});
  const [localViewport, setLocalViewport] = useState<[number, number] | null>(null);
  const viewport = timeInteraction?.viewport ?? localViewport;
  const setViewport = timeInteraction?.onViewport ?? setLocalViewport;
  useEffect(() => { if (!timeInteraction) setLocalViewport(null); }, [model]);
  const hidden = useMemo(
    () =>
      model.series
        .filter((s) => choices[s.id] ?? s.hidden ?? false)
        .map((s) => s.id),
    [model, choices],
  );
  return (
    <div className="native-chart">
      <div className="native-chart-stage" style={{ height: model.height }}>
        <ParentSize debounceTime={30}>
          {({ width }) =>
            width > 0 ? (
              <CartesianPlot
                model={model}
                width={width}
                hidden={hidden}
                viewport={viewport}
                onViewport={setViewport}
                onSelect={onSelect}
                timeInteraction={timeInteraction}
              />
            ) : null
          }
        </ParentSize>
      </div>
      {model.series.some((s) => s.showLegend) && (
        <div className="native-chart-legend" aria-label="Ряды графика">
          {model.series
            .filter((s) => s.showLegend)
            .map((s) => (
              <button
                key={s.id}
                type="button"
                aria-pressed={!hidden.includes(s.id)}
                onClick={() =>
                  setChoices({ ...choices, [s.id]: !hidden.includes(s.id) })
                }
              >
                <span
                  className="native-chart-swatch"
                  style={{ "--series-color": s.color } as CSSProperties}
                />
                {s.name}
              </button>
            ))}
        </div>
      )}
      {model.xAxis.type === "time" && model.data.length > 2 && timeInteraction?.showBrush !== false && (
        <div className="native-chart-note">
          <ExplanationTooltip
            label="Масштаб графика"
            content="Потяните границы полосы снизу, чтобы приблизить временной диапазон."
          />
          {viewport && (
            <button type="button" onClick={() => setViewport(null)}>
              Весь период
            </button>
          )}
        </div>
      )}
    </div>
  );
}
