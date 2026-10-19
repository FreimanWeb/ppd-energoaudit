import test from "node:test";
import assert from "node:assert/strict";
import {
  forecastTraces,
  wellSeries,
  filterEdges,
  sumDaily,
} from "./chartData.mjs";
test("forecast keeps interval order and distinguishes history from future", () => {
  const traces = forecastTraces({
    history: [{ period: -1, value: 7 }],
    forecast: [{ period: 1, value: 9, lower: 8, upper: 11 }],
    naive_baseline: 7,
  });
  assert.deepEqual(traces[0].y, [7]);
  assert.deepEqual(traces[1].y, [8]);
  assert.deepEqual(traces[2].y, [11]);
  assert.equal(traces[2].fill, "tonexty");
  assert.deepEqual(traces[3].y, [9]);
});
test("well monthly series never turns missing fact into zero", () => {
  assert.deepEqual(
    wellSeries(
      {
        totals: [{ month: "2026-01-01", fact: null }],
        rows: [
          { month: "2026-01-01", well: "1", fact: 0 },
          { month: "2026-02-01", well: "1", fact: null },
        ],
      },
      "1",
    ).map((x) => x.fact),
    [0, null],
  );
});
test("edge strength threshold preserves actual selected links only", () => {
  const edges = [
    { source: "1", target: "2", strength: 0.4 },
    { source: "2", target: "3", strength: 0.8 },
  ];
  assert.deepEqual(filterEdges(edges, 0.5, "2"), [edges[1]]);
  assert.deepEqual(filterEdges(edges, 0, "1"), [edges[0]]);
});
test("daily aggregate comparison sums same-date observed volumes only", () => {
  assert.deepEqual(
    sumDaily([
      ["2026-01-01", 3],
      ["2026-01-01", 2],
      ["2026-01-03", 4],
    ]),
    [
      ["2026-01-01", 5],
      ["2026-01-03", 4],
    ],
  );
});

const { lossChartData } = await import("./lossChartData.mjs");
test("loss charts retain signed components and supplied useful power", () => {
  const result = lossChartData(100, [
    { name: "Полезная", power_kw: 60, share: 0.6, category: "полезная" },
    { name: "Потери", power_kw: 45, share: 0.45, category: "потеря" },
    { name: "Коррекция", power_kw: -5, share: -0.05, category: "потеря" },
  ]);
  assert.deepEqual(result.waterfall.y, [100, -45, 5, 60]);
  assert.equal(result.waterfall.measure.at(-1), "absolute");
  assert.deepEqual(result.waterfall.tooltip.map(x => x.value), [100, 45, -5, 60]);
  assert.equal(result.waterfall.tooltip[0].selection, undefined);
  assert.equal(result.waterfall.tooltip[2].selection, "Коррекция");
});

const { downtimeForWell } = await import('./chartData.mjs');
test('CRM averages both series over the same dates and preserves factual zeros', async () => {
 const data = await import('./chartData.mjs');
 assert.equal(typeof data.compareDaily, 'function');
 assert.deepEqual(data.compareDaily([['2026-01-01', 1000], ['2026-01-02', 10], ['2026-01-03', 30]], [['2026-01-02', 0], ['2026-01-03', 20], ['2026-01-04', 9999]]), {
   count: 2, first: '2026-01-02', last: '2026-01-03', forecastMean: 20, factMean: 10,
 });
 assert.deepEqual(data.compareDaily([['2026-01-01', 1]], [['2026-01-02', 2]]), {
   count: 0, first: null, last: null, forecastMean: null, factMean: null,
 });
});
test('downtime markers use canonical well key and require an actual reason',()=>{
 const rows=[{well:'3592Д/2',well_key:'3592Д'}];
 const downtime=[{well:'3592Д',well_key:'3592Д',reason:'Ремонт',since:'2026-09-10T12:00'}];
 assert.equal(downtimeForWell('3592Д/2',rows,downtime),downtime[0]);
 assert.equal(downtimeForWell('2015',rows,downtime),null);
 assert.equal(downtimeForWell('3592Д/2',rows,[{...downtime[0],reason:''}]),null);
});

test('BG power is an intermediate total without adding a loss', async()=>{
 const {buildChartModel}=await import('../charts/chartModel.mjs');
 const items=[
  {name:'До БГ',power_kw:40,share:.4,category:'потеря'},
  {name:'Гидравлическая мощность на БГ',power_kw:60,share:.6,category:'промежуточная'},
  {name:'Трубы',power_kw:10,share:.1,category:'потеря'},
  {name:'Полезная мощность',power_kw:50,share:.5,category:'полезная'},
 ];
 const chart=lossChartData(100,items);
 assert.deepEqual(chart.waterfall.measure,['absolute','relative','absolute','relative','absolute']);
 assert.deepEqual(buildChartModel([chart.waterfall]).waterfall.map(p=>[p.start,p.end]),[[0,100],[100,60],[0,60],[60,50],[0,50]]);
});

test('aggregate overview groups pump to BG losses and retains signed and annual values', async()=>{
 const {aggregateLossGroups}=await import('./lossChartData.mjs');
 const items=[
  {name:'Полезная мощность',power_kw:60,share:.6,category:'полезная',annual_kwh:600,annual_rub:3000},
  {name:'Потери КПД',power_kw:-5,share:-.05,category:'потеря',annual_kwh:-50,annual_rub:-250},
  {name:'Номинальные',power_kw:30,share:.3,category:'потеря',annual_kwh:300,annual_rub:1500},
  {name:'Дросселирование',power_kw:10,share:.1,category:'потеря',annual_kwh:100,annual_rub:500},
  {name:'Гидравл. насос→БГ',power_kw:5,share:.05,category:'потеря',annual_kwh:50,annual_rub:250},
 ];
 const result=aggregateLossGroups(items);
 assert.equal(result.length,4);
 const combined=result.find(x=>x.name==='Потери на участке Насос–БГ');
 assert.equal(combined.power_kw,15);
 assert.ok(Math.abs(combined.share-.15)<1e-10);
 assert.equal(combined.annual_kwh,150);
 assert.equal(combined.annual_rub,750);
 assert.equal(result.find(x=>x.name==='Потери КПД').power_kw,-5);
 assert.equal(result.reduce((sum,x)=>sum+x.power_kw,0),100);
 assert.equal(items.length,5);
 const unknown=aggregateLossGroups(items.map(x=>x.name==='Гидравл. насос→БГ'?{...x,annual_kwh:null}:x));
 assert.equal(unknown.find(x=>x.name==='Потери на участке Насос–БГ').annual_kwh,null);
 assert.equal(aggregateLossGroups(items.filter(x=>!['Дросселирование','Гидравл. насос→БГ'].includes(x.name))).length,3);
});

test('chain overview uses eight columns with the wellhead boundary and signed nominal deviations',async()=>{
 const {chainLossGroups}=await import('./lossChartData.mjs');
 const {buildChartModel}=await import('../charts/chartModel.mjs');
 const balance={input_kw:100,bg_kw:75,output_kw:60,total_loss_kw:40,groups:[
  {id:'hall',power_kw:25,children:[{name:'Номинальные потери НА',power_kw:20},{name:'Отклонение от номинального КПД',power_kw:-5},{name:'Потери на участке Насос–БГ',power_kw:10}]},
  {id:'pipes',power_kw:5,children:[{name:'Трение',power_kw:3},{name:'Арматура',power_kw:2}]},
  {id:'wells',power_kw:10,children:[{name:'Штуцирование',power_kw:10}]},
 ]};
 const items=chainLossGroups(balance);
 const chart=lossChartData(balance.input_kw,items);
 assert.equal(chart.waterfall.x.length,8);
 assert.equal(chart.waterfall.x[4],'Гидравлическая мощность на БГ');
 assert.equal(chart.waterfall.x.at(-1),'Гидравлическая мощность на устьях');
 assert.deepEqual(chart.waterfall.y,[100,-20,5,-10,75,-5,-10,60]);
 assert.equal(items.filter(x=>x.category==='потеря').reduce((sum,x)=>sum+x.power_kw,0),40);
 assert.equal(items.filter(x=>x.category!=='промежуточная').reduce((sum,x)=>sum+x.share,0),1);
 assert.deepEqual(buildChartModel([chart.waterfall]).waterfall.map(x=>x.end),[100,80,85,75,75,70,60,60]);
 assert.deepEqual(chainLossGroups(null),[]);
 assert.deepEqual(chainLossGroups({...balance,groups:[]}),[]);
});
