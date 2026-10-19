import test from 'node:test';
import assert from 'node:assert/strict';
import {catalogMeasures,measureHref} from './features/losses/measureCatalog.mjs';

test('catalog keeps independent units, stage identities and unknown capital costs',()=>{
  const annual=[{measure_id:'restore',name:'Restore',cls:'сценарная оценка',energy_saving_kwh:100,money_saving_krub:5,capex_krub:0,payback_years:null}];
  const measures=[{id:'clean',name:'Clean',loss_name:'Трение в трубопроводах',description:'With head adjustment',saving_kw:9,saving_pct:2}];
  const rows=catalogMeasures(annual,{status:'scenario',measures});
  assert.deepEqual(rows.map(row=>[row.id,row.stage,row.value,row.unit]),[['annual:restore','hall',100,'кВт·ч/год'],['network:clean','pipes',9,'кВт']]);
  assert.equal(rows[0].capex,null);
  assert.equal(rows[1].capex,null);
  assert.equal(catalogMeasures(annual,{status:'infeasible',measures}).length,1);
  assert.equal(catalogMeasures([{...annual[0],energy_saving_kwh:NaN}],{status:'scenario',measures:[{...measures[0],saving_kw:-2}]}).length,0);
});

test('measure URLs replace stale focus and preserve the measurement and history period',()=>{
  const href=measureHref('network:clean','pipes',null,'http://localhost/?object=demo-ppd&aggregate=НА-1&day=2026-10-18&timestamp=2026-10-18T22:00:00&start=2026-09-19&inspect=eta_unit#pipelines');
  const url=new URL(href,'http://localhost');
  assert.equal(url.hash,'#measures');assert.equal(url.searchParams.get('measure'),'network:clean');
  assert.equal(url.searchParams.get('stage'),'pipes');assert.equal(url.searchParams.has('inspect'),false);
  assert.equal(url.searchParams.get('timestamp'),'2026-10-18T22:00:00');assert.equal(url.searchParams.get('start'),'2026-09-19');
  const station=new URL(measureHref('annual:restore','hall',{objectId:'demo-ppd',aggregateId:'НА-2',source:'telemetry',timestamp:'2026-10-17T20:00:00'},url.href),'http://localhost');
  assert.equal(station.searchParams.get('aggregate'),'НА-2');assert.equal(station.searchParams.get('day'),'2026-10-17');
});

test('choking measures belong to the BG-to-wellhead section',()=>{
  const rows=catalogMeasures([],{status:'scenario',measures:[{id:'head',name:'Head',loss_name:'Штуцирование скважин',description:'',saving_kw:5,saving_pct:1}]});
  assert.equal(rows[0].stage,'pipes');
});


test('hydraulic measure links carry custom parameters and unrelated cards clear them',()=>{
  const context={objectId:'demo-ppd',aggregateId:'НА-1',source:'telemetry',timestamp:'2026-10-18T22:00:00',networkScenario:{roughness_mm:.2}};
  const url=new URL(measureHref('network:clean_pipes','pipes',context,'http://localhost/?start=2026-09-19#network-scenario'),'http://localhost');
  assert.deepEqual(JSON.parse(url.searchParams.get('network_scenario')),context.networkScenario);
  assert.equal(url.searchParams.get('timestamp'),context.timestamp);
  assert.equal(url.searchParams.get('start'),'2026-09-19');
  const filtered=new URL(measureHref(null,'pipes',null,url.href),'http://localhost');
  assert.equal(filtered.searchParams.get('network_scenario'),url.searchParams.get('network_scenario'));
  const normal=new URL(measureHref(null,'pipes',{...context,networkScenario:undefined},url.href),'http://localhost');
  assert.equal(normal.searchParams.has('network_scenario'),false);
});
