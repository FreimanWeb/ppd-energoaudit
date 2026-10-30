export const PIPELINE_NODE_WIDTH=160;

/**
 * @param {import('./PipelineSchematic').SchematicPipeline[]} pipelines
 * @param {import('./PipelineSchematic').SchematicWell[]} wells
 */
export function pipelineTopology(pipelines,wells) {
  const byName=new Map(pipelines.map(pipe=>[pipe.name,pipe]));
  /** @type {Map<string,import('./PipelineSchematic').SchematicNode>} */
  const nodes=new Map();
  /** @type {Map<string,{source:string,target:string,uncertain:boolean}>} */
  const edges=new Map();
  for(const well of [...wells].sort((a,b)=>a.well.localeCompare(b.well,'ru',{numeric:true}))){
    const names=well.path_pipeline_names ?? [];
    const path=[...new Set(names)];
    const complete=well.path_complete && path.length>0 && path.length===names.length;
    const root=complete ? 'station' : 'unknown';
    nodes.set(root,{id:root,kind:complete ? 'source' : 'unknown',label:complete ? 'КНС / БГ' : 'Начало не установлено',x:0,y:0});
    let source=root;
    for(const name of path){
      const id=`pipe:${name}`,pipe=byName.get(name);
      const end=pipe?.end ?? name.match(/Скв\s+([0-9A-Za-zА-Яа-я]+)\s*-\s*\d+\s*$/)?.[1];
      nodes.set(id,{id,kind:'pipe',label:end ? `до ${end}` : name.slice(-24),pipe,x:0,y:0});
      const key=JSON.stringify([source,id]);
      const existing=edges.get(key);
      edges.set(key,{source,target:id,uncertain:!complete && (existing?.uncertain ?? true)});
      source=id;
    }
    const id=`well:${well.well}`;
    nodes.set(id,{id,kind:'well',label:`Скв ${well.well}`,well,x:0,y:0});
    edges.set(JSON.stringify([source,id]),{source,target:id,uncertain:!complete});
  }
  const links=[...edges.values()];
  const placed=new Set(),visiting=new Set();
  let row=0;
  /** @param {string} id @param {number} depth @returns {number} */
  function place(id,depth){
    const node=nodes.get(id);
    if(placed.has(id)) return node.y;
    visiting.add(id);
    const children=links.filter(edge=>edge.source===id && !visiting.has(edge.target));
    const ys=children.map(edge=>place(edge.target,depth+1));
    node.x=24+depth*(PIPELINE_NODE_WIDTH+40);
    node.y=ys.length ? (Math.min(...ys)+Math.max(...ys))/2 : 24+row++*80;
    // Shared or cyclic paths can reach a column twice; keep their boxes separate.
    while([...placed].some(other=>nodes.get(other).x===node.x && Math.abs(nodes.get(other).y-node.y)<68)) node.y+=80;
    visiting.delete(id);placed.add(id);
    return node.y;
  }
  for(const root of ['station','unknown']) if(nodes.has(root)) place(root,0);
  for(const id of nodes.keys()) if(!placed.has(id)) place(id,0);
  if(nodes.has('station')) nodes.get('station').y=24;
  const items=[...nodes.values()];
  return {nodes:items,edges:links,width:Math.max(500,...items.map(node=>node.x+PIPELINE_NODE_WIDTH+24)),height:Math.max(140,...items.map(node=>node.y+90))};
}
