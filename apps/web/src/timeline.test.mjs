import test from 'node:test';
import assert from 'node:assert/strict';
import { timelineSignal, recentPeriod, latestMetricPoint, timelineFocus } from './features/monitoring/timeline.mjs';

test('history inserts a null between missing two-hour samples without inventing values', () => {
  const points = [{ timestamp: '2026-07-01T00:00:00', value: 3 }, { timestamp: '2026-07-01T06:00:00', value: 5 }];
  assert.deepEqual(timelineSignal(points, 'value', 2).map(p => p.value), [3, null, 5]);
  assert.equal(points.length, 2);
});
test('daily history is kept daily, missing values and zero remain distinct', () => {
  const points = [{ timestamp: '2026-07-01T00:00:00', value: 0 }, { timestamp: '2026-07-02T00:00:00', value: null }];
  assert.deepEqual(timelineSignal(points, 'value', 24).map(p => p.value), [0, null]);
});
test('recent period uses latest available date, includes requested number of dates', () => {
  assert.deepEqual(recentPeriod('2026-07-01T22:00:00', 7), { start: '2026-06-25', end: '2026-07-01' });
});

test('mixed daily and interval measurements have a visible discontinuity', () => {
  const points = [
    { timestamp: '2026-07-01T00:00:00', sec_kwh_m3: 3, basis: 'daily' },
    { timestamp: '2026-07-02T00:00:00', sec_kwh_m3: 4, basis: 'daily' },
    { timestamp: '2026-07-02T02:00:00', sec_kwh_m3: 5, basis: 'interval' },
  ];
  assert.deepEqual(timelineSignal(points, 'sec_kwh_m3', 2).map(p => p.value), [3, 4, null, 5]);
});
test('latest KPI retains its own timestamp across partial union samples and preserves zero', () => {
  const points = [
    { timestamp: '2026-07-01T00:00:00', sec: 3, power: null },
    { timestamp: '2026-07-01T02:00:00', sec: null, power: 0 },
    { timestamp: '2026-07-01T04:00:00', sec: null, power: NaN },
  ];
  assert.equal(latestMetricPoint(points, 'sec'), points[0]);
  assert.equal(latestMetricPoint(points, 'power'), points[1]);
  assert.equal(latestMetricPoint(points, 'absent'), undefined);
});
test('daily SEC ignores unrelated hourly observations and keeps explicit missing days', () => {
  const first = { timestamp: '2026-07-01T00:00:00', sec_kwh_m3: 3, basis: 'daily', quality: 'partial' };
  const unrelated = { timestamp: '2026-07-01T02:00:00', sec_kwh_m3: null, power_kw: 15, basis: 'none', quality: 'partial' };
  const second = { timestamp: '2026-07-02T00:00:00', sec_kwh_m3: 4, basis: 'daily', quality: 'partial' };
  assert.deepEqual(timelineSignal([first, unrelated, second], 'sec_kwh_m3', 2).map(p => p.value), [3, 4]);
  assert.ok(timelineSignal([first, { ...second, sec_kwh_m3: null, quality: 'missing' }, { ...second, timestamp: '2026-07-03T00:00:00' }], 'sec_kwh_m3', 2).some(p => p.value === null));
});
test('power ignores unrelated daily calculation rows and calculation basis changes', () => {
  const points = [
    { timestamp: '2026-07-01T00:00:00', power_kw: 10, basis: 'daily', quality: 'partial' },
    { timestamp: '2026-07-01T01:00:00', power_kw: null, basis: 'daily', quality: 'partial' },
    { timestamp: '2026-07-01T02:00:00', power_kw: 12, basis: 'none', quality: 'partial' },
  ];
  assert.deepEqual(timelineSignal(points, 'power_kw', 2).map(p => p.value), [10, 12]);
});
test('unavailable SEC in a calculation row remains a gap', () => {
  const points = [
    { timestamp: '2026-07-01T00:00:00', sec_kwh_m3: 3, basis: 'daily', quality: 'partial' },
    { timestamp: '2026-07-02T00:00:00', sec_kwh_m3: null, basis: 'daily', quality: 'partial' },
    { timestamp: '2026-07-03T00:00:00', sec_kwh_m3: 4, basis: 'daily', quality: 'partial' },
  ];
  assert.deepEqual(timelineSignal(points, 'sec_kwh_m3', 2).map(p => p.value), [3, null, 4]);
});
test('inspection default is limited to displayed history and disabled for empty history', () => {
  const history = [
    { timestamp: '2026-06-01T00:00:00', snapshot_timestamp: '2026-06-01T22:00:00', quality: 'partial' },
    { timestamp: '2026-06-02T00:00:00', snapshot_timestamp: null, quality: 'partial' },
  ];
  assert.equal(timelineFocus(history), history[0]);
  assert.equal(timelineFocus([]), undefined);
  assert.equal(timelineFocus([{ ...history[1], quality: 'missing' }]), undefined);
});
test('daily volume and energy retain daily cadence through unrelated sensor rows', () => {
  const points = [
    { timestamp: '2026-07-01T00:00:00', volume_m3: 100, energy_kwh: 300, basis: 'daily', quality: 'partial' },
    { timestamp: '2026-07-01T02:00:00', volume_m3: null, energy_kwh: null, basis: 'none', quality: 'partial' },
    { timestamp: '2026-07-02T00:00:00', volume_m3: 110, energy_kwh: 310, basis: 'daily', quality: 'partial' },
  ];
  assert.deepEqual(timelineSignal(points, 'volume_m3', 2).map(p => p.value), [100, 110]);
  assert.deepEqual(timelineSignal(points, 'energy_kwh', 2).map(p => p.value), [300, 310]);
});
