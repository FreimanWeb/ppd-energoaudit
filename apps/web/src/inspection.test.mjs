import test from 'node:test';
import assert from 'node:assert/strict';
import { chainInspectionItems, inspectionFor, inspectionHref, lossHref, lossInspectionKey, relatedMeasures, sourceKeys } from './features/inspection/inspection.mjs';
test('inspection links preserve explicit measurement and reject unknown keys',()=>{
 const url=new URL(inspectionHref('sources','sec_fact','http://localhost/?object=a&aggregate=b&day=2026-01-01&timestamp=x&mode=analysis#overview'));
 assert.equal(url.searchParams.get('timestamp'),'x');
 assert.equal(url.searchParams.get('aggregate'),'b');
 assert.equal(url.searchParams.get('inspect'),'sec_fact');
 assert.equal(url.hash,'#sources');
 assert.equal(new URL(inspectionHref('losses','eta_unit',url.href)).hash,'#machine-losses');
 assert.equal(inspectionFor('__proto__'),undefined);
 assert.equal(new URL(inspectionHref('sources','bogus',url.href)).searchParams.has('inspect'),false);
});
test('measure relationship comes from registered basis, not its name or saving amount',()=>{
 const rows=[{name:'КПД',addresses:'ΔW_кпд (44)'},{name:'КПД',addresses:'ΔW_дрос (45)'},{name:'КПД'}];
 assert.deepEqual(relatedMeasures(rows,'efficiency_loss'),[rows[0]]);
 assert.deepEqual(relatedMeasures(rows,'sec_fact'),[]);
 assert.deepEqual(relatedMeasures(rows,'throttle_loss'),[rows[1]]);
 assert.deepEqual(relatedMeasures(rows,'unknown'),[]);
});
test('source evidence distinguishes measured fact and regime-derived SEC',()=>{
 const audit={scope:{daily_kpi_is_fact:true},regime:{q_fact:null},quality:{basis:{power:'W_сут / T_сут'}}};
 assert.deepEqual(sourceKeys('sec_fact',audit),['w','q_day']);
 audit.scope.daily_kpi_is_fact=false;
 assert.deepEqual(sourceKeys('sec_fact',audit),['w','q_day']);
 assert.deepEqual(sourceKeys('sec_regime',audit),['q_day','t','p_electric','w']);
});
test('loss bars resolve to stable inspection keys and stage pages',()=>{
 assert.equal(lossInspectionKey('Потери КПД'),'efficiency_loss');
 assert.equal(lossInspectionKey('Потери на участке Насос–БГ'),'pump_bg_loss');
 assert.equal(lossInspectionKey('Потери ЭД'),'motor_chain_loss');
 assert.equal(lossInspectionKey('Трение в стволах скважин'),'bore_loss');
 assert.equal(lossInspectionKey('__proto__'),undefined);
 assert.equal(lossInspectionKey('Непридуманная статья'),undefined);
});
test('loss href keeps analysis context and routes each article to its stage',()=>{
 const url=new URL(lossHref('throttle_loss','http://localhost/?object=a&aggregate=b&day=2026-01-01&timestamp=x&mode=analysis&keep=1#losses'));
 assert.equal(url.searchParams.get('inspect'),'throttle_loss');
 assert.equal(url.searchParams.get('timestamp'),'x');
 assert.equal(url.searchParams.get('keep'),'1');
 assert.equal(url.hash,'#machine-losses');
 assert.equal(new URL(lossHref('bore_loss',url.href)).hash,'#wells');
 assert.equal(new URL(lossHref('friction_loss',url.href)).hash,'#pipelines');
 assert.equal(new URL(lossHref('vfd_loss',url.href)).hash,'#machine-losses');
});

const outputScenario = {
 status: 'scenario',
 items: [{name:'Полезная закачка',category:'полезная',power_kw:100,provenance:'synthetic',basis:'Давление пласта'}],
 operator_balance: {boundary:'wellhead_after_choke',bg_kw:300,output_kw:139.41},
};
test('wellhead output is not replaced by useful injection downstream of bore losses',()=>{
 const wellhead=chainInspectionItems(lossInspectionKey('Гидравлическая мощность на устьях'),outputScenario);
 const injection=chainInspectionItems(lossInspectionKey('Полезная закачка'),outputScenario);
 assert.deepEqual(wellhead?.map(item=>item.power_kw),[139.41]);
 assert.deepEqual(injection?.map(item=>item.power_kw),[100]);
});
test('missing or incompatible boundary never substitutes a downstream quantity',()=>{
 const key=lossInspectionKey('Гидравлическая мощность на устьях');
 for(const operator_balance of [undefined,{boundary:'reservoir',output_kw:100}])
  assert.deepEqual(chainInspectionItems(key,{...outputScenario,operator_balance}),[]);
 assert.deepEqual(chainInspectionItems(key,{...outputScenario,status:'infeasible'}),[]);
});
test('a zero wellhead output remains an available calculated quantity',()=>{
 const selected=chainInspectionItems(lossInspectionKey('Гидравлическая мощность на устьях'),{
  ...outputScenario,operator_balance:{...outputScenario.operator_balance,output_kw:0},
 });
 assert.deepEqual(selected?.map(item=>item.power_kw),[0]);
});
