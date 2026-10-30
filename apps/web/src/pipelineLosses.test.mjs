import test from 'node:test';
import assert from 'node:assert/strict';

const {pipelineLosses}=await import('./features/losses/pipelineLosses.mjs');
const segment=(pipeline_id,power_kw,length_m=100)=>({id:pipeline_id,pipeline_id,name:pipeline_id,power_kw,length_m,flow_m3h:10,pressure_loss_mpa:power_kw/10});
const well=(id,path_pipeline_ids,armature_loss_kw,choke_loss_kw)=>({id,path_pipeline_ids,armature_loss_kw,choke_loss_kw});

test('shared trunk friction is counted once and well losses belong to terminal branches',()=>{
 const segments=[segment('main',10),segment('a',3),{...segment('a',2),id:'a2'},segment('b',4)];
 const wells=[well('1',['main','a'],1,5),well('2',['main','b'],2,6)];
 const original=JSON.stringify({segments,wells});
 const result=pipelineLosses(segments,wells);
 const main=result.pipelines.find(p=>p.id==='main'),a=result.pipelines.find(p=>p.id==='a');
 assert.equal(result.pipelines.length,3);
 assert.equal(main.friction_kw,10);
 assert.equal(main.local_kw,0);
 assert.equal(main.choke_kw,0);
 assert.equal(main.total_kw,10);
 assert.equal(main.wells.length,2);
 assert.equal(main.shared,true);
 assert.equal(a.friction_kw,5);
 assert.equal(a.length_m,200);
 assert.equal(a.local_kw,1);
 assert.equal(a.choke_kw,5);
 assert.equal(a.total_kw,11);
 assert.equal(result.pipelines.reduce((sum,p)=>sum+p.total_kw,0),33);
 assert.equal(result.unassignedWells.length,0);
 assert.equal(JSON.stringify({segments,wells}),original);
});

test('infeasible choking stays unknown and never becomes zero',()=>{
 const result=pipelineLosses([segment('a',0)],[well('1',['a'],0,null)]);
 assert.equal(result.pipelines[0].friction_kw,0);
 assert.equal(result.pipelines[0].choke_kw,null);
 assert.equal(result.pipelines[0].total_kw,null);
});

test('missing and unmatched routes are not attributed to an arbitrary pipeline',()=>{
 const wells=[well('1',[],1,2),well('2',['missing'],3,4),well('3',undefined,5,6)];
 const result=pipelineLosses([segment('a',3)],wells);
 assert.equal(result.unassignedWells.length,3);
 assert.equal(result.pipelines[0].wells.length,0);
 assert.equal(result.pipelines[0].total_kw,3);
 assert.deepEqual(pipelineLosses([],[]),{pipelines:[],unassignedWells:[]});
});
