export const stageDefinitions = [
  {id:"hall",label:"Машинный зал и обвязка",names:["Потери ПЧ","Потери ЭД","Потери передачи","Потери насоса","Гидравлика насос→БГ"]},
  {id:"pipes",label:"Трубопроводы",names:["Трение в трубопроводах"]},
  {id:"wells",label:"Скважины и арматура",names:["Арматура сети и скважин","Трение в стволах скважин","Штуцирование скважин"]},
];

/** @param {{status?:string,total_loss_kw?:number|null,items?:{name:string,power_kw:number,category:string}[]}|null|undefined} data */
export function networkStages(data) {
  if (data?.status !== "scenario" || !Number.isFinite(data.total_loss_kw) || !(data.total_loss_kw > 0)) return [];
  const losses = (data.items ?? []).filter(item => item.category === "потеря");
  if (losses.some(item => !Number.isFinite(item.power_kw) || item.power_kw < 0 || !stageDefinitions.some(group => group.names.includes(item.name)))) return [];
  const stages = stageDefinitions.map(group => ({
    id:group.id,label:group.label,
    power_kw:losses.filter(item => group.names.includes(item.name)).reduce((sum,item) => sum + item.power_kw,0),
  }));
  if (Math.abs(stages.reduce((sum,stage) => sum + stage.power_kw,0) - data.total_loss_kw) > Math.max(1,data.total_loss_kw) * 1e-6) return [];
  return stages.map(stage => ({...stage,share_pct:stage.power_kw / data.total_loss_kw * 100}));
}
