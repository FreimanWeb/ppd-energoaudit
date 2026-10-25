import test from 'node:test';
import assert from 'node:assert/strict';
import {pipelineTopology} from './features/network/pipelineTopology.mjs';

const pipes = ['trunk','a','b'].map(name => ({name,start:'БГ',end:name,length_m:100,sizes:'89×6'}));
const well = (id,path,complete=true) => ({well:id,path_pipeline_names:path,path_complete:complete});

test('shared pipelines appear once and both downstream wells keep their routes',()=>{
  const wells=[well('1',['trunk','a']),well('2',['trunk','b'])];
  const before=JSON.stringify({pipes,wells});
  const graph=pipelineTopology(pipes,wells);
  assert.equal(graph.nodes.filter(node=>node.kind==='pipe').length,3);
  assert.equal(graph.edges.filter(edge=>edge.target==='pipe:trunk').length,1);
  assert.ok(graph.edges.some(edge=>edge.source==='pipe:trunk' && edge.target==='pipe:a'));
  assert.ok(graph.edges.some(edge=>edge.source==='pipe:b' && edge.target==='well:2'));
  assert.equal(JSON.stringify({pipes,wells}),before);
  assert.equal(new Set(graph.nodes.map(node=>`${node.x}:${node.y}`)).size,graph.nodes.length);
});

test('partial and missing routes never gain a connection to the station',()=>{
  const graph=pipelineTopology(pipes,[well('1',['a'],false),well('2',[],false)]);
  assert.ok(!graph.edges.some(edge=>edge.source==='station'));
  assert.ok(graph.edges.some(edge=>edge.source==='unknown' && edge.target==='pipe:a' && edge.uncertain));
  assert.ok(graph.edges.some(edge=>edge.source==='unknown' && edge.target==='well:2' && edge.uncertain));
});

test('missing hydraulic parameters do not erase a resolved pipeline',()=>{
  const graph=pipelineTopology(pipes,[well('1',['absent','a'])]);
  assert.ok(graph.nodes.some(node=>node.id==='pipe:absent' && !node.pipe));
  assert.ok(graph.edges.some(edge=>edge.source==='station' && edge.target==='pipe:absent'));
});

test('cyclic routes terminate without invented station links',()=>{
  const graph=pipelineTopology(pipes,[well('2',['a','b','a'],false),well('3',['b','a'],false)]);
  assert.ok(graph.nodes.every(node=>Number.isFinite(node.x) && Number.isFinite(node.y)));
  assert.ok(!graph.edges.some(edge=>edge.source==='station'));
  assert.ok(graph.width>0 && graph.height>0);
});
