export const chartTheme = { green:'var(--chart-status-success)',gray:'var(--chart-secondary)',red:'var(--chart-status-danger)',amber:'var(--chart-status-warning)',text:'var(--chart-ink)',grid:'var(--chart-grid)',surface:'var(--chart-surface)' };
export const chartColors = [chartTheme.green,chartTheme.amber,chartTheme.gray,chartTheme.red,'var(--chart-primary-alt)'];
const colors = {'#1f4e4a':chartTheme.green,'#426b80':chartTheme.gray,'#8b9892':chartTheme.gray,'#c58b25':chartTheme.amber,'#c76e62':chartTheme.red,'#b34a42':chartTheme.red};
const color = (value,fallback=chartTheme.green) => colors[value?.toLowerCase()]??value??fallback;
const at = (value,index,fallback) => (Array.isArray(value)?value[index]:value)??fallback;
const text = value => String(value??'').replace(/<br\s*\/?\s*>/gi,'\n').replace(/<[^>]*>/g,'');
const numeric = value => typeof value==='number'&&Number.isFinite(value)?value:null;
const coordinate = (value,type) => type==='time'?Date.parse(String(value)):type==='number'?numeric(value):String(value??'');
const axisType = (axis,values) => axis?.type==='category'?'category':axis?.type==='linear'?'number':axis?.type==='date'||values.some(value=>typeof value==='string'&&/^\d{4}-\d{2}-\d{2}(T|$)/.test(value))?'time':values.some(value=>typeof value==='string')?'category':'number';
const axis = (input,type) => ({type,label:input?.title?.text??'',hidden:input?.visible===false,reversed:input?.autorange==='reversed',...(input?.range?.length===2?{domain:input.range.map(v=>coordinate(v,type))}:{})});

/** @param {import('./types').Trace[]} traces @param {import('./types').Layout} layout @param {string} title @returns {import('./types').ChartModel} */
export function buildChartModel(traces,layout={},title='') {
 const base={...(layout.showBrush === false ? {showBrush:false}:{}),title,height:layout.height??360,margin:{top:layout.margin?.t??20,right:layout.margin?.r??24,bottom:layout.margin?.b??40,left:layout.margin?.l??55}};
 if(!traces.length) return {...base,kind:'empty',message:'Нет данных для графика.'};
 const first=traces[0];
 if(first.type==='sankey') return {...base,kind:'sankey',nodes:(first.node?.label??[]).map((name,i)=>({name:text(name),tooltip:first.node?.tooltip?.[i],color:color(at(first.node?.color,i,chartColors[i%chartColors.length]))})),links:(first.link?.value??[]).map((value,i)=>({source:first.link.source[i],target:first.link.target[i],value,tooltip:first.link.tooltip?.[i],color:color(at(first.link.color,i,'var(--chart-secondary)'))}))};
 if(first.type==='indicator') return {...base,title:first.title?.text??title,kind:'gauge',value:first.value??0,range:first.gauge?.axis?.range??[0,1],threshold:first.gauge?.threshold?.value,thresholdColor:color(first.gauge?.threshold?.line?.color,chartTheme.gray),color:color(first.gauge?.bar?.color),steps:first.gauge?.steps??[],valueFormat:first.number?.valueformat};
 const nodesTrace=traces.find(trace=>trace.customdata?.length&&trace.mode?.includes('markers'));
 if(nodesTrace){
  const nodes=(nodesTrace.x??[]).flatMap((x,i)=>{
   const y=nodesTrace.y?.[i],id=nodesTrace.customdata?.[i];
   if(numeric(x)===null||numeric(y)===null||typeof id!=='string') return [];
   return [{id,x,y,label:text(at(nodesTrace.text,i,id)),color:color(at(nodesTrace.marker?.color,i,chartTheme.green)),size:at(nodesTrace.marker?.size,i,12),shape:at(nodesTrace.marker?.symbol,i,'circle'),detail:text(at(nodesTrace.hovertext,i,''))}];
  });
  const edges=traces.filter(trace=>trace!==nodesTrace&&trace.mode?.includes('lines')).map(trace=>{
   const points=(trace.x??[]).flatMap((x,i)=>numeric(x)!==null&&numeric(trace.y?.[i])!==null?[{x,y:trace.y[i]}]:[]);
   const source=nodes.find(n=>n.x===points[0]?.x&&n.y===points[0]?.y)?.id;
   const target=nodes.find(n=>n.x===points.at(-1)?.x&&n.y===points.at(-1)?.y)?.id;
   return {source,target,points,color:color(trace.line?.color,chartTheme.gray),width:trace.line?.width??1,label:text(trace.text)};
  });
  return {...base,kind:'network',nodes,edges};
 }
 const horizontal=traces.some(trace=>trace.orientation==='h');
 const coordinates=traces.flatMap(trace=>(horizontal?trace.y:trace.x)??[]);
 const categoryType=axisType(horizontal?layout.yaxis:layout.xaxis,coordinates);
 const categoryAxis=axis(horizontal?layout.yaxis:layout.xaxis,categoryType);
 const numericAxis=axis(horizontal?layout.xaxis:layout.yaxis,'number');
 const model={...base,...(layout.categoryGroups?.length ? {categoryGroups:layout.categoryGroups} : {}),kind:'cartesian',variant:first.type==='waterfall'?'waterfall':'series',horizontal,stacked:['stack','relative'].includes(layout.barmode??''),xAxis:horizontal?numericAxis:categoryAxis,yAxis:horizontal?categoryAxis:numericAxis,references:[],annotations:[],series:[],data:[]};
 const categoryValue=value=>coordinate(value,categoryType);
 for(const shape of layout.shapes??[]){
  const axisName=shape.xref!=='paper'&&shape.x0===shape.x1?'x':shape.yref!=='paper'&&shape.y0===shape.y1?'y':null;
  if(!axisName) continue;
  const type=(axisName==='x'?model.xAxis:model.yAxis).type;
  model.references.push({axis:axisName,value:coordinate(axisName==='x'?shape.x0:shape.y0,type),color:color(shape.line?.color,chartTheme.gray),dashed:Boolean(shape.line?.dash&&shape.line.dash!=='solid')});
 }
 model.annotations=(layout.annotations??[]).map(item=>({x:item.xref==='paper'?undefined:coordinate(item.x,model.xAxis.type),y:item.yref==='paper'?undefined:coordinate(item.y,model.yAxis.type),text:text(item.text),color:color(item.font?.color,chartTheme.text),vertical:Number(item.textangle)===90}));
 if(first.type==='waterfall'){
  let running=0;
  model.waterfall=(first.y??[]).map((raw,i)=>{
   const value=numeric(raw)??0,measure=first.measure?.[i]??'relative';
   const start=measure==='relative'?running:0,end=measure==='total'?running:measure==='absolute'?value:running+value;
   running=end;
   return {label:text(first.x?.[i]),start,end,value,measure,tooltip:first.tooltip?.[i],color:color(measure==='relative'?(value<0?first.decreasing?.marker?.color:first.increasing?.marker?.color):first.totals?.marker?.color,measure==='relative'?(value<0?chartTheme.red:chartTheme.amber):chartTheme.green)};
  });
  model.data=model.waterfall.map(point=>({x:point.label,start:point.start,end:point.end,value:point.value,span:[Math.min(point.start,point.end),Math.max(point.start,point.end)]}));
  return model;
 }
 model.series=traces.map((trace,i)=>{
  const band=trace.fill==='tonexty'&&i>0;
  const coords=(horizontal?trace.y:trace.x)??[];
  const values=(horizontal?trace.x:trace.y)??[];
  const lower=band?traces[i-1]:null;
  const points=coords.map((x,j)=>{
   const label=trace.mode?.includes('markers')&&!trace.mode.includes('lines')?at(trace.text,j,at(trace.hovertext,j,x)):at(trace.hovertext,j,x);
   const point={x:categoryValue(x),y:numeric(values[j]),label:text(label),...(trace.tooltip?.[j]?{tooltip:trace.tooltip[j]}:{}),...(typeof trace.customdata?.[j]==='string'?{customdata:trace.customdata[j]}:{})};
   if(band){const index=lower.x?.findIndex(v=>v===x)??-1;point.low=numeric(lower.y?.[index]);point.high=point.y;}
   else{if(trace.type==='bar'&&Array.isArray(trace.marker?.color))point.color=color(trace.marker.color[j]);if(trace.mode?.includes('markers')){point.color=color(at(trace.marker?.color,j,trace.line?.color??chartColors[i%chartColors.length]));point.size=at(trace.marker?.size,j,7);point.shape=at(trace.marker?.symbol,j,'circle');}}
   return point;
  });
  return {id:`s${i}`,name:trace.name??(trace.type==='bar'?title:`Ряд ${i+1}`),type:band?'band':trace.type==='bar'?'bar':trace.mode&&!trace.mode.includes('lines')?'scatter':'line',points,color:color(trace.line?.color??(typeof trace.marker?.color==='string'?trace.marker.color:undefined),chartColors[i%chartColors.length]),dashed:Boolean(trace.line?.dash&&trace.line.dash!=='solid'),width:trace.line?.width??2,curve:trace.line?.shape==='hv'?'stepAfter':'linear',showLegend:trace.showlegend!==false,connectNulls:trace.connectgaps===true,fill:trace.fillcolor,markers:trace.mode?.includes('markers')??false,hidden:traces[i+1]?.fill==='tonexty'&&trace.line?.width===0};
 });
 const rows=new Map();
 for(const series of model.series)for(const point of series.points){
  if(!rows.has(point.x)) rows.set(point.x,{x:point.x,label:point.label});
  rows.get(point.x)[series.id]=series.type==='band'?(point.low!==null&&point.high!==null?[point.low,point.high]:null):point.y;
 }
 model.data=[...rows.values()];
 if(categoryType!=='category')model.data.sort((a,b)=>Number(a.x)-Number(b.x));
 for(const row of model.data)for(const series of model.series)if(!(series.id in row))row[series.id]=null;
 return model;
}
