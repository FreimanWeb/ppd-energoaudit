import test from "node:test";
import assert from "node:assert/strict";
import { networkStages } from "./features/losses/networkStages.mjs";

test("stage percentages use total losses rather than input power", () => {
  const data = {status:"scenario",input_kw:1000,total_loss_kw:200,items:[
    {name:"Потери насоса",power_kw:100,category:"потеря"},
    {name:"Трение в трубопроводах",power_kw:60,category:"потеря"},
    {name:"Штуцирование скважин",power_kw:40,category:"потеря"},
    {name:"Полезная мощность",power_kw:800,category:"полезная"},
  ]};
  const stages = networkStages(data);
  assert.deepEqual(stages.map(stage => stage.share_pct),[50,50,0]);
  assert.equal(stages.reduce((sum,stage) => sum + stage.power_kw,0),200);
  assert.deepEqual(networkStages({...data,status:"infeasible"}),[]);
  assert.deepEqual(networkStages({...data,total_loss_kw:0}),[]);
  assert.deepEqual(networkStages({...data,total_loss_kw:201}),[]);
  assert.deepEqual(networkStages({...data,items:[...data.items,{name:"Неизвестная потеря",power_kw:1,category:"потеря"}]}),[]);
});
