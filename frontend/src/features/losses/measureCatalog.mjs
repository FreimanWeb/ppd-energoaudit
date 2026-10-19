import {stageDefinitions} from './networkStages.mjs';

/** @typedef {{measure_id:string,name:string,cls:string,energy_saving_kwh:number,money_saving_krub:number,capex_krub:number,payback_years:number|null,note?:string,addresses?:string,aggregate_id?:string}} AnnualMeasure */
/** @typedef {{id:string,name:string,loss_name:string,description:string,saving_kw:number,saving_pct:number,assumptions?:string[]}} NetworkMeasure */
/** @param {AnnualMeasure[]} annual @param {{status:string,measures?:NetworkMeasure[]}|null} [network] */
export function catalogMeasures(annual = [], network = null) {
  return [
    ...annual.filter(row => Number.isFinite(row.energy_saving_kwh) && row.energy_saving_kwh > 0).sort((a,b)=>b.energy_saving_kwh-a.energy_saving_kwh).map(row => ({
      id:`annual:${row.measure_id}`, kind:'annual', stage:'hall', name:row.name,
      description:row.note || row.addresses || '', value:row.energy_saving_kwh, unit:'кВт·ч/год',
      money:row.money_saving_krub, capex:row.cls === 'сценарная оценка' ? null : row.capex_krub,
      payback:row.cls === 'сценарная оценка' ? null : row.payback_years, assumptions:[],
      intervention:null, aggregate:row.aggregate_id || '',
    })),
    ...(network?.status === 'scenario' ? network.measures ?? [] : [])
      .filter(row => Number.isFinite(row.saving_kw) && row.saving_kw > 0)
      .sort((a,b)=>b.saving_kw-a.saving_kw).flatMap(row => {
        const stage=stageDefinitions.find(stage=>stage.names.includes(row.loss_name));
        return stage ? [{id:`network:${row.id}`,kind:'network',stage:stage.id,name:row.name,
          description:row.description,value:row.saving_kw,unit:'кВт',money:null,capex:null,payback:null,
          assumptions:row.assumptions ?? [],intervention:row.id,aggregate:'',
        }] : [];
      }),
  ];
}

/** @param {string|null} id @param {string} stage @param {{objectId:string,aggregateId:string,source:string,timestamp:string,networkScenario?:Record<string,number>}|null} [context] @param {string} [href] */
export function measureHref(id,stage,context=null,href=location.href) {
  const url=new URL(href);
  url.searchParams.delete('inspect');
  if(id) url.searchParams.set('measure',id); else url.searchParams.delete('measure');
  if(stage) url.searchParams.set('stage',stage); else url.searchParams.delete('stage');
  if(context) {
    if(context.networkScenario) url.searchParams.set('network_scenario',JSON.stringify(context.networkScenario));
    else url.searchParams.delete('network_scenario');
    url.searchParams.set('object',context.objectId);
    url.searchParams.set('aggregate',context.aggregateId);
    url.searchParams.set('mode',context.source === 'field_trip' ? 'field_trip' : 'analysis');
    if(context.source === 'telemetry') {
      url.searchParams.set('day',context.timestamp.slice(0,10));url.searchParams.set('timestamp',context.timestamp);
    } else {url.searchParams.delete('day');url.searchParams.delete('timestamp');}
  }
  url.hash='measures';
  return `${url.pathname}${url.search}${url.hash}`;
}
