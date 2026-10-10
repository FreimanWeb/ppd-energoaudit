export type Datum = number | string | null;
export type Color = string;
export type AxisModel = { type: 'number' | 'time' | 'category'; label: string; domain?: [number | string, number | string]; hidden?: boolean; reversed?: boolean };
export type PointModel = { x: number | string; y: number | null; low?: number | null; high?: number | null; label?: string; color?: string; size?: number; shape?: string; customdata?: string };
export type SeriesModel = { id: string; name: string; type: 'line' | 'bar' | 'band' | 'scatter'; points: PointModel[]; color: string; dashed?: boolean; width: number; curve: 'linear' | 'stepAfter'; hidden?: boolean; showLegend: boolean; connectNulls: boolean; fill?: string; markers?: boolean };
export type ReferenceModel = { axis: 'x' | 'y'; value: number | string; color: string; dashed: boolean; label?: string };
export type AnnotationModel = { x?: number | string; y?: number | string; text: string; color: string; vertical?: boolean };
export type BaseModel = { title: string; height: number; margin: { top: number; right: number; bottom: number; left: number } };
export type WaterfallPoint = { label: string; start: number; end: number; value: number; measure: 'absolute' | 'relative' | 'total'; color: string };
export type CartesianModel = BaseModel & { kind: 'cartesian'; variant: 'series' | 'waterfall'; series: SeriesModel[]; data: Record<string, number | string | null | [number, number]>[]; xAxis: AxisModel; yAxis: AxisModel; horizontal: boolean; stacked: boolean; references: ReferenceModel[]; annotations: AnnotationModel[]; waterfall?: WaterfallPoint[] };
export type SankeyModel = BaseModel & { kind: 'sankey'; nodes: { name: string; color: string }[]; links: { source: number; target: number; value: number; color: string }[] };
export type GaugeModel = BaseModel & { kind: 'gauge'; value: number; range: [number, number]; threshold?: number; thresholdColor: string; color: string; steps: { range: [number, number]; color: string }[]; valueFormat?: string };
export type NetworkModel = BaseModel & { kind: 'network'; nodes: { id: string; x: number; y: number; label: string; color: string; size: number; shape: string; detail: string }[]; edges: { source?: string; target?: string; points: { x: number; y: number }[]; color: string; width: number; label: string }[] };
export type EmptyModel = BaseModel & { kind: 'empty'; message: string };
export type ChartModel = CartesianModel | SankeyModel | GaugeModel | NetworkModel | EmptyModel;

// Вход сохраняет только уже используемые свойства страниц при переходе renderer.
export type Trace = {
 type?: string;mode?: string;name?: string;x?: Datum[];y?: Datum[];text?: string|string[];customdata?: unknown[];hovertext?: string|string[];showlegend?: boolean;connectgaps?: boolean;fill?: string;fillcolor?: string;orientation?: string;measure?: string[];value?: number;hoverinfo?: string;hovertemplate?: string;textposition?: string;
 line?: {color?:string;width?:number;dash?:string;shape?:string}; marker?:{color?:string|string[];size?:number|number[];symbol?:string|string[]};
 node?:{label?:string[];color?:string|string[];pad?:number;thickness?:number};link?:{source?:number[];target?:number[];value?:number[];color?:string|string[]};arrangement?:string;
 title?:{text?:string};number?:{valueformat?:string};gauge?:{axis?:{range?:number[]};bar?:{color?:string};steps?:{range:number[];color:string}[];threshold?:{value?:number;line?:{color?:string;width?:number}}};connector?:{line?:{color?:string}};decreasing?:{marker?:{color?:string}};increasing?:{marker?:{color?:string}};totals?:{marker?:{color?:string}};
};
export type Layout = { height?:number;margin?:{l?:number;r?:number;t?:number;b?:number};barmode?:string;hovermode?:string;title?:{text?:string};xaxis?:AxisInput;yaxis?:AxisInput;shapes?:ShapeInput[];annotations?:{x?:Datum;y?:Datum;xref?:string;yref?:string;text?:string;font?:{color?:string;size?:number};textangle?:string|number;showarrow?:boolean;xanchor?:string;yanchor?:string}[] };
export type AxisInput = {type?:string;title?:{text?:string};range?:Datum[];visible?:boolean;autorange?:boolean|string;tickformat?:string;dtick?:number;gridcolor?:string;scaleanchor?:string};
export type ShapeInput = {type?:string;xref?:string;yref?:string;x0?:Datum;x1?:Datum;y0?:Datum;y1?:Datum;line?:{color?:string;dash?:string}};
