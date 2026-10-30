import {test} from 'node:test';
import assert from 'node:assert/strict';
import {gaugePoint} from './charts/specialChartData.mjs';

test('nominal gauge marker follows the actual scale and clamps physical arc endpoints',()=>{
  const start=gaugePoint(0,1,100,100,80);
  assert.equal(start.x,20);
  assert.ok(Math.abs(start.y-100)<1e-10);
  const mid=gaugePoint(.5,1,100,100,80);
  assert.ok(Math.abs(mid.x-100)<1e-10);
  assert.equal(mid.y,20);
  assert.equal(gaugePoint(2,1,100,100,80).x,180);
  assert.equal(gaugePoint(-1,1,100,100,80).x,20);
  assert.deepEqual(gaugePoint(1,0,100,100,80),start);
});

test('flow legend shows positive incoming energy without inventing total supplied power',async()=>{
  const {flowNodeValues}=await import('./charts/specialChartData.mjs');
  assert.deepEqual(flowNodeValues(3,[{source:0,target:1,value:100},{source:0,target:2,value:-20}]),[null,100,0]);
});

test('Sankey omits disconnected zero articles and remaps positive links without mutating inputs',async()=>{
  const {activeFlowGraph}=await import('./charts/specialChartData.mjs');
  const nodes=Object.freeze([{name:'Вход',color:'gray'},{name:'Нулевая статья',color:'red'},{name:'Полезная',color:'green'},{name:'Потеря',color:'red'}]);
  const links=Object.freeze([{source:0,target:1,value:0},{source:0,target:2,value:15},{source:0,target:3,value:5},{source:0,target:3,value:-1}]);
  const active=activeFlowGraph(nodes,links);
  assert.deepEqual(active.nodes.map(node=>node.originalIndex),[0,2,3]);
  assert.deepEqual(active.links.map(link=>[link.source,link.target,link.value]),[[0,1,15],[0,2,5]]);
  assert.ok(!active.nodes.some(node=>node.name==='Нулевая статья'));
  const {sankey}=await import('d3-sankey');
  const layout=sankey().extent([[12,20],[300,300]])(active);
  assert.ok(layout.nodes.every(node=>[node.x0,node.x1,node.y0,node.y1].every(Number.isFinite)));
  assert.equal(nodes[1].name,'Нулевая статья');
  assert.equal(links[1].target,2);
});
