import test from 'node:test';
import assert from 'node:assert/strict';
import { signalShape,economicDisplay } from './fidelity.mjs';
test('power and pressure are held states, while daily totals are discrete measurements',()=>{
 assert.equal(signalShape('Активная мощность','кВт'),'hv');
 assert.equal(signalShape('Давление на приёме','МПа'),'hv');
 assert.equal(signalShape('Энергия за сутки','кВт·ч'),'linear');
 assert.equal(signalShape('Объём за сутки','м³'),'linear');
});
test('scenario capital-dependent fields require assessment without changing actual benefit data',()=>{
 const original={cls:'сценарная оценка',capex_krub:0,npv_krub:990,irr:.4,payback_years:0,discounted_payback_years:0,total_money_krub:1000};
 const display=economicDisplay(original);
 for(const key of ['capex_krub','npv_krub','irr','payback_years','discounted_payback_years']) assert.equal(display[key],'Требует оценки');
 assert.equal(display.total_money_krub,1000);assert.equal(original.capex_krub,0);
});
test('confirmed costs preserve zero and unavailable IRR; IRR percentage is only presentation',()=>{
 const row=economicDisplay({cls:'техническое',capex_krub:0,irr:.25,payback_years:0,npv_krub:0});
 assert.equal(row.irr,25); assert.equal(row.capex_krub,0);assert.equal(row.npv_krub,0);assert.equal(row.payback_years,0);
 assert.equal(economicDisplay({cls:'техническое',irr:null}).irr,null);
});
