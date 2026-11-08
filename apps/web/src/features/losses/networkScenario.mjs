/** @template {{saving_kw: number, loss_name: string}} T
 * @param {string} status @param {T[]} measures @param {string} [selectedName]
 * @returns {T[]}
 */
export function networkMeasures(status, measures, selectedName = "") {
  if (status !== "scenario") return [];
  return measures.filter(measure => Number.isFinite(measure.saving_kw) && measure.saving_kw > 0 && (!selectedName || measure.loss_name === selectedName))
    .sort((a, b) => b.saving_kw - a.saving_kw);
}

export const scenarioParameters=[
  {key:'roughness_factor',label:'Множитель к справочной шероховатости труб и НКТ',value:1,min:0,max:10,step:0.1},
  {key:'well_depth_m',label:'Длина ствола скважины, м',value:1800,min:1,max:10000,step:1},
  {key:'well_diameter_mm',label:'Внутренний диаметр НКТ, мм',value:62,min:10,max:500,step:1},
  {key:'local_resistance_k',label:'Коэффициент местных сопротивлений',value:2,min:0,max:1000,step:0.1},
  {key:'useful_pressure_mpa',label:'Требуемое полезное давление без перепада высот, МПа',value:3,min:0,max:100,step:0.1},
  {key:'elevation_change_m',label:'Перепад высот от станции к скважинам, м',value:0,min:-1000,max:1000,step:1},
];

/** @param {string|null} value @returns {Record<string,number>|null} */
export function readNetworkScenario(value){
  if(!value) return null;
  try{
    const data=JSON.parse(value);
    if(!data || Array.isArray(data) || typeof data!=='object' || Object.keys(data).length!==scenarioParameters.length) return null;
    if(scenarioParameters.some(p=>!Number.isFinite(data[p.key]) || data[p.key]<p.min || data[p.key]>p.max)) return null;
    return Object.fromEntries(scenarioParameters.map(p=>[p.key,data[p.key]]));
  }catch{return null;}
}

/** @param {{status:string,operator_balance?:{bg_kw:number}|null,items?:{name:string,power_kw:number,share:number,category:string}[]}|null|undefined} data */
export function hydraulicLossMap(data){
  const power=data?.operator_balance?.bg_kw;
  if(data?.status!=='scenario' || typeof power!=='number' || !Number.isFinite(power) || power<=0) return null;
  const names=['Трение в трубопроводах','Арматура сети и скважин','Штуцирование скважин','Трение в стволах скважин'];
  const losses=names.flatMap(name=>(data.items ?? []).filter(item=>item.name===name)).concat((data.items ?? []).filter(item=>item.category==='полезная'))
    .map(item=>({...item,share:item.power_kw/power}));
  const total=losses.filter(item=>item.category==='потеря').reduce((sum,item)=>sum+item.power_kw,0);
  const useful=losses.filter(item=>item.category==='полезная').reduce((sum,item)=>sum+item.power_kw,0);
  return {input_kw:power,losses,total_loss_kw:total,useful_kw:useful,balance_error_kw:power-total-useful};
}
