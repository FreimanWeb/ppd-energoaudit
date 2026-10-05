/** @param {string} metric @param {string} unit */
export function signalShape(metric,unit) {
 return /давлен|p_|pвх|pвых/i.test(metric)||unit==='кВт' ? 'hv' : 'linear';
}
/** @template {{cls:string,irr?:number|null}} T @param {T} row */
export function economicDisplay(row) {
 const fields=['capex_krub','npv_krub','irr','payback_years','discounted_payback_years'];
 return {...row,...Object.fromEntries(fields.filter(key=>key in row).map(key=>[
  key,row.cls==='сценарная оценка'?'Требует оценки':key==='irr'&&row.irr!=null?row.irr*100:row[key],
 ]))};
}
