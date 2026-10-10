import test from 'node:test';
import assert from 'node:assert/strict';
import { buildChartModel } from './chartModel.mjs';
test('time axes preserve held signals, null gaps and reference annotations',()=>{
 const model=buildChartModel([{type:'scatter',name:'Мощность',x:['2026-09-29T00:00:00','2026-09-29T01:00:00'],y:[0,null],line:{shape:'hv'}}],{xaxis:{type:'date'},yaxis:{title:{text:'кВт'}},shapes:[{xref:'x',x0:'2026-09-29T00:30:00',x1:'2026-09-29T00:30:00',yref:'paper',y0:0,y1:1,line:{dash:'dot'}}],annotations:[{x:'2026-09-29T00:30:00',yref:'paper',y:1,text:'2017: Ремонт'}]},'Телеметрия');
 assert.equal(model.kind,'cartesian');assert.equal(model.xAxis.type,'time');assert.equal(model.series[0].curve,'stepAfter');assert.deepEqual(model.series[0].points.map(p=>p.y),[0,null]);assert.equal(model.series[0].connectNulls,false);assert.equal(model.data[1].s0,null);assert.equal(model.references[0].axis,'x');assert.equal(model.annotations[0].text,'2017: Ремонт');
});
test('forecast uncertainty is an actual lower-upper area, not a fill down to zero',()=>{
 const model=buildChartModel([{type:'scatter',x:[1,2],y:[8,7],line:{width:0},showlegend:false},{type:'scatter',name:'Интервал',x:[1,2],y:[11,10],fill:'tonexty',line:{width:0},fillcolor:'#eee'},{type:'scatter',name:'Прогноз',x:[1,2],y:[9,8]}]);
 assert.equal(model.series[1].type,'band');assert.deepEqual(model.data[0].s1,[8,11]);assert.deepEqual(model.series[1].points[1],{x:2,y:10,low:7,high:10,label:'2'});assert.equal(model.series[0].hidden,true);
});
test('signed waterfall keeps corrections and supplied final absolute power',()=>{
 const model=buildChartModel([{type:'waterfall',x:['Подвод','Потери','Коррекция','Полезная'],y:[100,-45,5,60],measure:['absolute','relative','relative','absolute']}]);
 assert.equal(model.variant,'waterfall');assert.deepEqual(model.waterfall.map(p=>[p.start,p.end,p.value]),[[0,100,100],[100,55,-45],[55,60,5],[0,60,60]]);
});
test('horizontal stacked shares preserve signs and categorical labels',()=>{
 const model=buildChartModel([{type:'bar',orientation:'h',name:'Полезная',x:[60],y:['']},{type:'bar',orientation:'h',name:'Коррекция',x:[-5],y:['']}],{barmode:'relative'});
 assert.equal(model.horizontal,true);assert.equal(model.stacked,true);assert.equal(model.series[1].points[0].y,-5);assert.equal(model.yAxis.type,'category');assert.equal(model.data[0].s1,-5);
});
test('gauge threshold, Sankey links and graph IDs survive renderer migration',()=>{
 const gauge=buildChartModel([{type:'indicator',value:0,gauge:{axis:{range:[0,1]},threshold:{value:.7},steps:[{range:[0,.5],color:'red'}]}}]);assert.equal(gauge.kind,'gauge');assert.equal(gauge.value,0);assert.equal(gauge.threshold,.7);
 const flow=buildChartModel([{type:'sankey',node:{label:['Вход','Полезная']},link:{source:[0],target:[1],value:[60]}}]);assert.equal(flow.kind,'sankey');assert.equal(flow.links[0].value,60);
 const graph=buildChartModel([{type:'scatter',mode:'lines',x:[0,1],y:[0,1],text:'Связь2015↔2017'},{type:'scatter',mode:'text+markers',x:[0,1],y:[0,1],text:['2015','2017'],customdata:['well-a','well-b'],marker:{symbol:['circle','square'],size:[12,20]},hovertext:['','Ремонт']}]);
 assert.equal(graph.kind,'network');assert.equal(graph.nodes[1].id,'well-b');assert.equal(graph.nodes[1].shape,'square');assert.equal(graph.nodes[1].detail,'Ремонт');assert.equal(graph.edges[0].target,'well-b');
});
test('an explicit categorical date label is not silently converted to a timeline',()=>{
 const model=buildChartModel([{type:'bar',x:['2026-09-29'],y:[5]}],{xaxis:{type:'category'}});
 assert.equal(model.xAxis.type,'category');assert.equal(model.data[0].x,'2026-09-29');
});
test('timeline union is chronological, equal moments share one row, and explicit gaps remain null',()=>{
 const x=['2026-09-29T01:00:00Z','2026-09-29T00:00:00Z'];
 const model=buildChartModel([{type:'scatter',mode:'lines',name:'Факт',x,y:[null,0]},{type:'scatter',mode:'lines',name:'Прогноз',x:['2026-09-29T00:00:00Z','2026-09-29T02:00:00Z'],y:[4,5]}],{xaxis:{type:'date'}});
 assert.deepEqual(model.data.map(r=>[r.s0,r.s1]),[[0,4],[null,null],[null,5]]);
 assert.equal(model.series[0].hidden,false);assert.equal(model.series[1].hidden,false);
 const cost=buildChartModel([{type:'scatter',x:[0,1],y:[0,20]}],{shapes:[{xref:'paper',x0:0,x1:1,yref:'y',y0:0,y1:0,line:{dash:'dot'}}]});
 assert.equal(cost.references[0].axis,'y');assert.equal(cost.references[0].value,0);
});
test('marker-only points use supplied factual labels while lines retain timestamp tooltip labels',()=>{
 const markers=buildChartModel([{type:'scatter',mode:'markers+text',x:[120,180],y:[1400,1500],text:['Факт','Номинал']}]);
 assert.deepEqual(markers.series[0].points.map(p=>p.label),['Факт','Номинал']);
 const hover=buildChartModel([{type:'scatter',mode:'markers',x:[120],y:[1400],hovertext:['Рабочая точка']}]);
 assert.equal(hover.series[0].points[0].label,'Рабочая точка');
 const line=buildChartModel([{type:'scatter',mode:'lines+markers',x:['2026-09-29T01:00:00'],y:[0],text:['Комментарий']}]);
 assert.equal(line.series[0].points[0].label,'2026-09-29T01:00:00');
});
