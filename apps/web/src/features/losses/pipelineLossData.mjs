/**
 * @param {import('./PipelineLosses').PipelineSegment[]} segments
 * @param {import('./PipelineLosses').PipelineWell[]} wells
 */
export function pipelineLosses(segments,wells) {
  /** @type {Map<string,import('./PipelineLosses').PipelineSegment[]>} */
  const grouped=new Map();
  for(const section of segments){
    const sections=grouped.get(section.pipeline_id) ?? [];
    sections.push(section);
    grouped.set(section.pipeline_id,sections);
  }
  const pipelines=[...grouped].map(([id,sections])=>{
    const connected=wells.filter(well=>well.path_pipeline_ids?.includes(id));
    const terminal=connected.filter(well=>well.path_pipeline_ids?.at(-1) === id);
    const friction_kw=sections.reduce((sum,section)=>sum+section.power_kw,0);
    const local_kw=terminal.reduce((sum,well)=>sum+well.armature_loss_kw,0);
    const choke_kw=terminal.every(well=>typeof well.choke_loss_kw === 'number' && Number.isFinite(well.choke_loss_kw))
      ? terminal.reduce((sum,well)=>sum+Number(well.choke_loss_kw),0) : null;
    return {
      id,name:sections[0].name,sections,wells:connected,shared:connected.length>1,
      length_m:sections.reduce((sum,section)=>sum+section.length_m,0),
      flow_m3h:sections[0].flow_m3h,friction_kw,local_kw,choke_kw,
      total_kw:choke_kw === null ? null : friction_kw+local_kw+choke_kw,
    };
  });
  const unassignedWells=wells.filter(well=>!grouped.has(well.path_pipeline_ids?.at(-1)));
  return {pipelines,unassignedWells};
}
