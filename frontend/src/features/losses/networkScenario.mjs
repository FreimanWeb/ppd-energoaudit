/** @template {{saving_kw: number, loss_name: string}} T
 * @param {string} status @param {T[]} measures @param {string} [selectedName]
 * @returns {T[]}
 */
export function networkMeasures(status, measures, selectedName = "") {
  if (status !== "scenario") return [];
  return measures.filter(measure => Number.isFinite(measure.saving_kw) && measure.saving_kw > 0 && (!selectedName || measure.loss_name === selectedName))
    .sort((a, b) => b.saving_kw - a.saving_kw);
}
