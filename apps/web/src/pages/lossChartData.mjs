/** @param {number} input @param {{name:string,power_kw:number,share:number,category:string}[]} items */
export function lossChartData(input, items, inputLabel="Подведённая мощность") {
  const useful = items.find((x) => x.category === "полезная");
  const bars = items.filter((x) => x.category === "потеря" || x.category === "промежуточная");
  return {
    waterfall: {
      type: "waterfall",
      orientation: "v",
      measure: ["absolute", ...bars.map(x => x.category === "промежуточная" ? "absolute" : "relative"), "absolute"],
      x: [
        inputLabel,
        ...bars.map((x) => x.name),
        useful?.name ?? "Полезная мощность",
      ],
      y: [input, ...bars.map((x) => x.category === "промежуточная" ? x.power_kw : -x.power_kw), useful?.power_kw ?? 0],
      tooltip: [{ value: input, unit: "кВт", share: input > 0 ? 1 : undefined },
        ...bars.map(x => ({ value: x.power_kw, unit: "кВт", share: x.share, selection: x.name })),
        { value: useful?.power_kw ?? 0, unit: "кВт", share: useful?.share, selection: useful?.name }],
      connector: { line: { color: "#d5dedb" } },
      decreasing: { marker: { color: "#c76e62" } },
      increasing: { marker: { color: "#c58b25" } },
      totals: { marker: { color: "#1f4e4a" } },
    },

  };
}

/** @param {import('../shared/types').Audit['losses']} items @param {boolean} [detailed] */
export function aggregateLossGroups(items, detailed=false) {
  const names=["Дросселирование","Гидравл. насос→БГ"];
  const combined=items.filter(item=>names.includes(item.name));
  if(!combined.length) return items;
  const order=["Полезная мощность","Номинальные","Потери КПД","Износ","Неоптимальная подача","Дросселирование","Гидравл. насос→БГ"];
  const ordered=[...items].sort((a,b)=>(order.indexOf(a.name)<0 ? order.length : order.indexOf(a.name))-(order.indexOf(b.name)<0 ? order.length : order.indexOf(b.name)));
  if(detailed) return ordered;
  /** @param {'annual_kwh'|'annual_rub'} key */
  const annual=key=>combined.every(item=>typeof item[key] === "number")
    ? combined.reduce((sum,item)=>sum+Number(item[key]),0) : null;
  return [...ordered.filter(item=>!names.includes(item.name)),{
    ...combined[0],name:"Потери на участке Насос–БГ",
    power_kw:combined.reduce((sum,item)=>sum+item.power_kw,0),
    share:combined.reduce((sum,item)=>sum+item.share,0),
    annual_kwh:annual("annual_kwh"),annual_rub:annual("annual_rub"),
  }];
}

/** @param {{input_kw:number,bg_kw:number,output_kw:number,groups:{id:string,power_kw:number,children:{name:string,power_kw:number}[]}[]}|null|undefined} balance */
export function chainLossGroups(balance) {
  if(!balance) return [];
  const hall=balance.groups.find(group=>group.id === "hall");
  const pipes=balance.groups.find(group=>group.id === "pipes");
  const wells=balance.groups.find(group=>group.id === "wells");
  if(!hall || !pipes || !wells) return [];
  /** @param {string} name @param {number} power_kw @param {string} category */
  const item=(name,power_kw,category)=>({name,power_kw,share:power_kw/balance.input_kw,category});
  return [
    ...hall.children.map(child=>item(child.name,child.power_kw,"потеря")),
    item("Гидравлическая мощность на БГ",balance.bg_kw,"промежуточная"),
    item("Потери в трубопроводах",pipes.power_kw,"потеря"),
    item("Штуцирование нагнетательных скважин",wells.power_kw,"потеря"),
    item("Гидравлическая мощность на устьях",balance.output_kw,"полезная"),
  ];
}
