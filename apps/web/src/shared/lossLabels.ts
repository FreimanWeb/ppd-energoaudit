import dictionary from '../../../../shared/loss-labels.json' with {type:'json'};

export const lossLabels=dictionary.labels;
export function lossLabel(name:string):string {
  const key=(dictionary.aliases as Record<string,string>)[name];
  return (lossLabels as Record<string,string>)[key] ?? name;
}
