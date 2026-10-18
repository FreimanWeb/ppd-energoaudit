import test from 'node:test';
import assert from 'node:assert/strict';
import { inspectionFor, inspectionHref, relatedMeasures, sourceKeys } from './features/inspection/inspection.mjs';
test('inspection links preserve explicit measurement and reject unknown keys',()=>{
 const url=new URL(inspectionHref('sources','sec_fact','http://localhost/?object=a&aggregate=b&day=2026-01-01&timestamp=x&mode=analysis#overview'));
 assert.equal(url.searchParams.get('timestamp'),'x');
 assert.equal(url.searchParams.get('aggregate'),'b');
 assert.equal(url.searchParams.get('inspect'),'sec_fact');
 assert.equal(url.hash,'#sources');
 assert.equal(new URL(inspectionHref('losses','eta_unit',url.href)).hash,'#machine-block');
 assert.equal(inspectionFor('__proto__'),undefined);
 assert.equal(new URL(inspectionHref('sources','bogus',url.href)).searchParams.has('inspect'),false);
});
test('measure relationship comes from registered basis, not its name or saving amount',()=>{
 const rows=[{name:'КПД',addresses:'ΔW_кпд (44)'},{name:'КПД',addresses:'ΔW_дрос (45)'},{name:'КПД'}];
 assert.deepEqual(relatedMeasures(rows,'sec_fact'),[rows[0]]);
 assert.deepEqual(relatedMeasures(rows,'p_bg'),[rows[1]]);
 assert.deepEqual(relatedMeasures(rows,'unknown'),[]);
});
test('source evidence distinguishes daily fact and calculated regime',()=>{
 const audit={scope:{daily_kpi_is_fact:true},regime:{q_fact:null},quality:{basis:{power:'W_сут / T_сут'}}};
 assert.deepEqual(sourceKeys('sec_fact',audit),['w','q_day']);
 audit.scope.daily_kpi_is_fact=false;
 assert.deepEqual(sourceKeys('sec_fact',audit),['q_day','t','p_electric','w']);
});
