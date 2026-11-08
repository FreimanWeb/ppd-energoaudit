import assert from "node:assert/strict";
import test from "node:test";
import { networkMeasures,hydraulicLossMap,readNetworkScenario,scenarioParameters } from "./features/losses/networkScenario.mjs";

const measures = [
  { id: "pipes", loss_name: "Трубы", saving_kw: 3 },
  { id: "head", loss_name: "Штуцеры", saving_kw: 9 },
  { id: "invalid", loss_name: "Трубы", saving_kw: NaN },
  { id: "zero", loss_name: "Трубы", saving_kw: 0 },
];
test("network measures rank positive finite savings without changing source order", () => {
  assert.deepEqual(networkMeasures("scenario", measures).map(row => row.id), ["head", "pipes"]);
  assert.equal(measures[0].id, "pipes");
});
test("network measures match the selected chain component", () => {
  assert.deepEqual(networkMeasures("scenario", measures, "Трубы").map(row => row.id), ["pipes"]);
  assert.deepEqual(networkMeasures("scenario", measures, "Полезная мощность"), []);
});
test("unavailable and infeasible balances expose no savings", () => {
  assert.deepEqual(networkMeasures("infeasible", measures), []);
  assert.deepEqual(networkMeasures("unavailable", measures), []);
});


test("hydraulic map starts at BG, rebases shares and preserves the physical balance",()=>{
  const item=(name,power_kw,category='потеря')=>({name,power_kw,share:power_kw/100,category});
  const data={status:'scenario',input_kw:100,operator_balance:{bg_kw:60},items:[
    item('Потери насоса',40),item('Трение в трубопроводах',5),item('Арматура сети и скважин',1),
    item('Трение в стволах скважин',10),item('Штуцирование скважин',14),item('Полезная закачка',30,'полезная'),
  ]};
  const original=JSON.stringify(data);
  const map=hydraulicLossMap(data);
  assert.equal(map.input_kw,60);assert.equal(map.total_loss_kw,30);assert.equal(map.useful_kw,30);
  assert.equal(map.balance_error_kw,0);
  assert.deepEqual(map.losses.map(row=>row.name),['Трение в трубопроводах','Арматура сети и скважин','Штуцирование скважин','Трение в стволах скважин','Полезная закачка']);
  assert.ok(Math.abs(map.losses.reduce((sum,row)=>sum+row.share,0)-1)<1e-10);
  assert.equal(map.losses[0].share,5/60);
  assert.equal(JSON.stringify(data),original);
  assert.equal(hydraulicLossMap({...data,status:'infeasible'}),null);
  assert.equal(hydraulicLossMap({...data,operator_balance:{bg_kw:0}}),null);
  assert.equal(hydraulicLossMap({...data,operator_balance:null}),null);
});

test('scenario handoff accepts only complete finite parameters inside model bounds',()=>{
  const scenario=Object.fromEntries(scenarioParameters.map(p=>[p.key,p.value]));
  scenario.roughness_factor=.5;
  assert.deepEqual(readNetworkScenario(JSON.stringify(scenario)),scenario);
  for(const invalid of [null,'oops','[]','null',JSON.stringify({...scenario,roughness_factor:'0.5'}),JSON.stringify({...scenario,roughness_factor:11}),JSON.stringify({...scenario,extra:1}),JSON.stringify({roughness_factor:.5})]) assert.equal(readNetworkScenario(invalid),null);
});
