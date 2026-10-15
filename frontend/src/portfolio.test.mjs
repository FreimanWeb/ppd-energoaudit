import test from 'node:test';
import assert from 'node:assert/strict';
import { visibleObjects, sparklinePoints } from './features/monitoring/portfolio.mjs';

test('portfolio filters and ranks attention first without mutating the source', () => {
  const objects = [
    {code:'a',name:'Север',ngdu_name:'НГДУ 1',water_type:'Пластовая',status:'normal'},
    {code:'b',name:'Юг',ngdu_name:'НГДУ 1',water_type:'Пластовая',status:'attention'},
    {code:'c',name:'Запад',ngdu_name:'НГДУ 2',water_type:'Пресная',status:'unknown'},
  ];
  assert.deepEqual(visibleObjects(objects, '', [], [], 'all').map(o=>o.code), ['b','a','c']);
  assert.deepEqual(visibleObjects(objects, 'юГ', ['НГДУ 1'], ['Пластовая'], 'attention').map(o=>o.code), ['b']);
  assert.equal(visibleObjects(objects, '', ['НГДУ 2'], ['Пластовая'], 'all').length, 0);
  assert.equal(objects[0].code, 'a');
});

test('sparkline preserves null gaps and uses elapsed time on the horizontal axis', () => {
  const history = [
    {timestamp:'2026-01-01T00:00:00',value:2},
    {timestamp:'2026-01-01T02:00:00',value:null},
    {timestamp:'2026-01-01T06:00:00',value:4},
    {timestamp:'2026-01-01T08:00:00',value:3},
  ];
  const points = sparklinePoints(history);
  assert.equal(points.length, 4);
  assert.equal(points[1], null);
  assert.ok(points[2].x > 150 && points[2].x < 200);
  assert.ok(points[0].y > points[2].y);
  assert.deepEqual(sparklinePoints([]), []);
  assert.ok(sparklinePoints([{timestamp:'2026-01-01',value:2}]).every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
});

test('sparkline recalculates horizontal positions for its container without scaling vertical positions', () => {
  const history = [{timestamp:'2026-01-01',value:2}, {timestamp:'2026-01-02',value:4}];
  const original = sparklinePoints(history);
  const wide = sparklinePoints(history, 600);
  assert.equal(wide[0].x, 8);
  assert.equal(wide[1].x, 592);
  assert.deepEqual(wide.map(point => point.y), original.map(point => point.y));
});

test('sparkline hover selects the nearest available date regardless of vertical position', async () => {
  const { nearestSparklinePoint } = await import('./features/monitoring/portfolio.mjs');
  assert.equal(typeof nearestSparklinePoint, 'function');
  const points = [{x:10,y:100}, null, {x:100,y:0}];
  assert.equal(nearestSparklinePoint(points, 12), 0);
  assert.equal(nearestSparklinePoint(points, 90), 2);
  assert.equal(nearestSparklinePoint(points, 55), 0);
  assert.equal(nearestSparklinePoint([null], 10), null);
});

test('sparkline leaves empty space up to the selected end date instead of stretching old data', () => {
  const points = sparklinePoints([
    {timestamp:'2026-10-01T00:00:00',value:2},
    {timestamp:'2026-10-03T00:00:00',value:4},
  ], 600, 128, {start:'2026-10-01',end:'2026-10-07'});
  assert.equal(points[0].x, 8);
  assert.ok(points[1].x > 170 && points[1].x < 180);
});

test('portfolio periods select calendar days relative to each object latest measurement and retain gaps', async () => {
  const { portfolioHistory } = await import('./features/monitoring/portfolio.mjs');
  assert.equal(typeof portfolioHistory, 'function');
  const history = [
    {timestamp:'2026-09-24T22:00:00',value:2},
    {timestamp:'2026-09-25T00:00:00',value:3},
    {timestamp:'2026-09-27T00:00:00',value:null},
    {timestamp:'2026-10-01T02:00:00',value:4},
    {timestamp:'2026-10-02T00:00:00',value:5},
  ];
  const week = portfolioHistory(history, '2026-10-01T23:30:00', 7);
  assert.deepEqual(week, {start:'2026-09-25',end:'2026-10-01',history:history.slice(1,4)});
  assert.deepEqual(portfolioHistory(history, '2026-10-01T23:30:00', 1).history, [history[3]]);
  assert.equal(portfolioHistory(history, '2026-10-01T23:30:00', 30).start, '2026-09-02');
  assert.deepEqual(portfolioHistory([], null, 7), {start:'',end:'',history:[]});
  assert.equal(history.length, 5);
});
