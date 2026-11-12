import test from 'node:test';
import assert from 'node:assert/strict';
import { previousPeriod, summarizePeriod, periodChange } from './features/monitoring/periodComparisonData.mjs';

test('previous calendar period has the same inclusive duration including leap dates',()=>{
  assert.deepEqual(previousPeriod('2024-03-01','2024-03-07'),{start:'2024-02-23',end:'2024-02-29'});
  assert.equal(previousPeriod('','2024-03-07'),null);
  assert.equal(previousPeriod('2024-03-07','2024-03-01'),null);
});
test('daily SEC uses matched sums, never mean ratios or unmatched totals',()=>{
  const s=summarizePeriod([
    {basis:'daily',energy_kwh:100,volume_m3:10},
    {basis:'daily',energy_kwh:100,volume_m3:100},
    {basis:'daily',energy_kwh:999,volume_m3:null},
    {basis:'none',energy_kwh:null,volume_m3:null},
  ],'2026-10-01','2026-10-03');
  assert.equal(s.sec,200/110);assert.equal(s.energy,200);assert.equal(s.volume,110);
  assert.equal(s.paired,2);assert.equal(s.expected,3);
});
test('instantaneous samples do not invent energy or volume; stops and invalid values are excluded',()=>{
  const s=summarizePeriod([
    {basis:'interval',power_kw:0,flow_m3h:10},
    {basis:'interval',power_kw:100,flow_m3h:20},
    {basis:'interval',power_kw:100,flow_m3h:0},
    {basis:'interval',power_kw:NaN,flow_m3h:20},
  ],'2026-10-01','2026-10-01');
  assert.equal(s.sec,100/30);assert.equal(s.energy,null);assert.equal(s.volume,null);
  assert.equal(s.paired,2);assert.equal(s.expected,12);assert.equal(s.stopped,1);
});
test('mixed bases cannot produce a misleading SEC and no data is not zero',()=>{
  const s=summarizePeriod([{basis:'daily',energy_kwh:10,volume_m3:2},{basis:'interval',power_kw:20,flow_m3h:2}],'2026-10-01','2026-10-02');
  assert.equal(s.basis,'mixed');assert.equal(s.sec,null);
  assert.equal(summarizePeriod([],'2026-10-01','2026-10-02').sec,null);
  assert.equal(periodChange(0,10),null);assert.equal(periodChange(10,0),-100);assert.equal(periodChange(null,10),null);
});

test('comparison profiles align calendar starts, retain real dates and break gaps',async()=>{
  const {comparisonProfile}=await import('./features/monitoring/periodComparisonData.mjs');
  const points=[
    {timestamp:'2026-10-01T00:00:00',basis:'interval',quality:'ready',power_kw:100,flow_m3h:20},
    {timestamp:'2026-10-01T01:00:00',basis:'none',quality:'partial',p_in_mpa:1},
    {timestamp:'2026-10-01T06:00:00',basis:'interval',quality:'ready',power_kw:120,flow_m3h:20},
    {timestamp:'2026-10-01T08:00:00',basis:'interval',quality:'ready',power_kw:120,flow_m3h:0},
  ];
  const profile=comparisonProfile(points,'2026-10-01','interval',2);
  assert.deepEqual(profile.map(p=>p.value),[5,null,6,null]);
  assert.equal(profile[0].day,0);assert.equal(profile[2].day,.25);
  assert.equal(profile[2].timestamp,points[2].timestamp);
  const shifted=comparisonProfile([{...points[0],timestamp:'2026-10-08T00:00:00'}],'2026-10-08','interval',2);
  assert.equal(shifted[0].day,profile[0].day);
});
test('daily profiles align by date, preserve zero SEC and exclude unrelated snapshots',async()=>{
  const {comparisonProfile}=await import('./features/monitoring/periodComparisonData.mjs');
  const profile=comparisonProfile([
    {timestamp:'2026-10-01T23:00:00',basis:'daily',quality:'ready',energy_kwh:0,volume_m3:10},
    {timestamp:'2026-10-02T00:00:00',basis:'none',quality:'partial'},
    {timestamp:'2026-10-03T22:00:00',basis:'daily',quality:'ready',energy_kwh:20,volume_m3:10},
  ],'2026-10-01','daily',2);
  assert.deepEqual(profile.map(p=>p.value),[0,null,2]);
  assert.equal(profile[0].day,0);assert.equal(profile[2].day,2);
});
