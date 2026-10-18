import { useState } from "react";
import { Plot } from "../../charts/Plot";
import { segment, useResource } from "../../shared/api";
import { Panel } from "../../shared/ui/Panel";
import { Status } from "../../shared/ui/Status";
import { Table } from "../../shared/ui/Table";
import "./wellHistory.css";

type WellRecord = {
  observed_at: string; grain: "snapshot" | "month" | "day";
  record_kind: "current" | "monthly_actual" | "monthly_reported" | "study";
  metric: string; value: number; unit: string; study_type: string | null;
  source_file: string; source_sheet: string; source_row: number; exported_at: string | null;
};
type Wells = {
  wells: { code: string; latest_at: string | null; current_at: string | null }[];
  density_default: { density_kgm3: number; available_from: string; source: string } | null;
};
type History = { well_code: string; records: WellRecord[]; warnings: string[] };

const labels: Record<string, string> = {
  flow_m3_day: "Приёмистость", p_well_before_choke: "Давление до штуцера",
  p_well_after_choke: "Давление после штуцера", p_well: "Давление на устье",
  p_bg: "Давление на БГ", p_reservoir: "Пластовое давление",
  p_bottomhole: "Забойное давление", p_study: "Давление при исследовании",
  injection_volume_m3: "Объём закачки", runtime_hours: "Время работы",
  downtime_hours: "Время простоя", restricted_hours: "Работа с ограничениями",
  density_kgm3: "Плотность жидкости",
};
const columns = [
  { key: "period", label: "Дата / месяц" }, { key: "metric", label: "Показатель" },
  { key: "value", label: "Значение", digits: 3 }, { key: "unit", label: "Единица" },
  { key: "study", label: "Исследование" }, { key: "source", label: "Источник" },
  { key: "exported", label: "Выгрузка" },
];
function recordRows(records: WellRecord[]) {
  return records.map(record => ({
    period: record.grain === "month" ? record.observed_at.slice(0, 7) : record.observed_at,
    metric: labels[record.metric] ?? record.metric, value: record.value, unit: record.unit,
    study: record.study_type ?? "—",
    source: `${record.source_file} · ${record.source_sheet}, строка ${record.source_row}`,
    exported: record.exported_at ?? "Не указана",
  }));
}

export function WellHistory({ objectId }: { objectId: string }) {
  const wells = useResource<Wells>(`/objects/${segment(objectId)}/wells`);
  const [selection, setSelection] = useState({ objectId, code: "" });
  const code = selection.objectId === objectId && wells.data?.wells.some(well => well.code === selection.code)
    ? selection.code : wells.data?.wells[0]?.code ?? "";
  const history = useResource<History>(code ? `/objects/${segment(objectId)}/wells/${segment(code)}/history` : null);
  const records = history.data?.records ?? [];
  const monthly = records.filter(record => record.record_kind === "monthly_actual");
  const current = records.filter(record => record.record_kind === "current");
  const studies = records.filter(record => record.record_kind === "study");
  const exports = [...new Set(records.map(record => record.exported_at).filter(Boolean))].sort();
  const pressureSeries = ["p_well", "p_bg"].map((metric, index) => {
    const points = monthly.filter(record => record.metric === metric && record.unit === "атм")
      .sort((a, b) => a.observed_at.localeCompare(b.observed_at));
    return {
      type: "scatter", mode: "markers", name: labels[metric],
      x: points.map(record => record.observed_at), y: points.map(record => record.value),
      marker: { color: index ? "var(--chart-secondary)" : "var(--chart-primary)" },
    };
  }).filter(series => series.x.length);

  return <Panel title="История нагнетательных скважин" caption="Архив устьевых давлений, закачки и исследований">
    <div className="well-history">
      <p className="notice">Это архив: дата текущего режима — дата выгрузки, фактическая дата измерения не подтверждена, месячная динамика — к целому месяцу, ГДИ — к отдельным исследованиям. Двухчасовой телеметрии скважин здесь нет. Пересчёт «атм» в МПа требует подтверждения единиц; эти давления пока не подставляются автоматически в карту потерь.</p>
      <Status {...wells} />
      {wells.data?.density_default && <p className="muted">Плотность объекта: {wells.data.density_default.density_kgm3} кг/м³. Получена {wells.data.density_default.available_from}; источник: {wells.data.density_default.source}. Это значение объекта, а не замена измерениям плотности в ГДИ.</p>}
      {wells.data && (wells.data.wells.length ? <>
        <label className="well-history-select"><span>Нагнетательная скважина</span>
          <select value={code} onChange={event => setSelection({ objectId, code: event.target.value })}>
            {wells.data.wells.map(well => <option key={well.code} value={well.code}>{well.code}</option>)}
          </select>
        </label>
        <Status {...history} />
        {history.data && <>
          {exports.length > 0 && <p className="muted">Даты выгрузок: {exports.join(", ")}. Это даты получения архива, а не даты всех измерений.</p>}
          {history.data.warnings.map((warning, index) => <p key={index} className="notice">{warning}</p>)}
          {pressureSeries.length > 0 ? <section aria-label="Месячные давления скважины">
            <h3>Давление на устье и на БГ по месяцам</h3>
            <p className="muted">Месячные фактические записи, атм. Дата на оси обозначает месяц; между записями нет интерполяции. Отчётные записи хранятся отдельно в таблице ниже.</p>
            <Plot title="Месячные давления скважины" data={pressureSeries} layout={{ xaxis: { type: "date" }, yaxis: { title: { text: "атм" } } }} />
          </section> : <p className="notice">Месячных фактических давлений для графика нет.</p>}
          <section aria-label="Архивный текущий режим"><h3>Текущий режим по архиву</h3>
            <Table rows={recordRows(current)} columns={columns} />
          </section>
          <details><summary>ГДИ: история исследований ({studies.length} записей)</summary>
            <Table rows={recordRows(studies)} columns={columns} />
          </details>
          <details><summary>Месячные записи и источники ({records.filter(record => record.grain === "month").length})</summary>
            <p className="muted">«Фактические» и «отчётные» строки не объединяются и могут отличаться.</p>
            <Table rows={records.filter(record => record.grain === "month").map(record => ({
              ...recordRows([record])[0], kind: record.record_kind === "monthly_actual" ? "Фактические" : "Отчётные",
            }))} columns={[{ key: "kind", label: "Вид записи" }, ...columns]} />
          </details>
        </>}
      </> : <p className="notice">История скважин для объекта ещё не импортирована.</p>)}
    </div>
  </Panel>;
}
