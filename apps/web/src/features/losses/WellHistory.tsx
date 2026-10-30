import { useEffect } from "react";
import { LinkButton } from "../../shared/ui/Button";
import { setWellSelection, useWellSelection, wellHref } from "../../shared/wellSelection";
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
  const selection = useWellSelection();
  const firstCode = wells.data?.wells[0]?.code;
  useEffect(() => {
    if (!selection && firstCode) setWellSelection(firstCode);
  }, [selection, firstCode]);
  const code = selection || wells.data?.wells[0]?.code || "";
  const missing = Boolean(selection && wells.data && !wells.data.wells.some(well => well.code === selection));
  const history = useResource<History>(code && wells.data && !missing ? `/objects/${segment(objectId)}/wells/${segment(code)}/history` : null);
  const records = history.data?.records ?? [];
  const monthly = records.filter(record => record.record_kind === "monthly_actual");
  const current = records.filter(record => record.record_kind === "current");
  const studies = records.filter(record => record.record_kind === "study");
  const exports = [...new Set(records.map(record => record.exported_at).filter(Boolean))].sort();
  const pressureSeries = ["p_well", "p_bg"].map((metric, index) => {
    const points = monthly.filter(record => record.metric === metric && record.unit === "атм")
      .sort((a, b) => a.observed_at.localeCompare(b.observed_at));
    return {
      type: "scatter", mode: "lines+markers", name: labels[metric],
      x: points.map(record => record.observed_at), y: points.map(record => record.value),
      marker: { color: index ? "var(--chart-secondary)" : "var(--chart-primary)" },
    };
  }).filter(series => series.x.length);

  return <Panel title="История нагнетательных скважин" caption="Архив устьевых давлений, закачки и исследований">
    <div className="well-history">
      <p className="notice">{objectId === "demo-ppd" ? "Демонстрационные данные: синтетический архив для проверки интерфейса." : "Архив скважин независим от выбранного режима НА. Давления в исходных атм; для автоматического использования в карте потерь нужны подтверждённые единицы."}</p>
      <Status {...wells} />
      {wells.data && (wells.data.wells.length || selection ? <>
        <label className="well-history-select"><span>Нагнетательная скважина</span>
          <select aria-label="Нагнетательная скважина" value={code} onChange={event => setWellSelection(event.target.value)}>
            {missing && <option value={selection}>{selection} · нет в архиве</option>}
            {wells.data.wells.map(well => <option key={well.code} value={well.code}>{well.code}</option>)}
          </select>
        </label>
        {missing && <p className="notice">Скважина {selection} отсутствует в архиве этого объекта. {wells.data.wells.length ? "Выберите скважину из списка." : "Архив объекта ещё не импортирован."} Выбранный код сохранён для других разделов.</p>}
        {!missing && code && <div><LinkButton href={wellHref("crm-wells", code)}>Прогноз по скважине · CRM</LinkButton></div>}
        {!missing && <Status {...history} />}
        {history.data && <>
          <details><summary>Качество и источники архива</summary>
            <p className="muted">Дата текущего режима — дата выгрузки; фактическая дата измерения не подтверждена. Месячные записи относятся к целому месяцу, ГДИ — к отдельным исследованиям. Двухчасовой телеметрии здесь нет.</p>
            {exports.length > 0 && <p className="muted">Даты выгрузок: {exports.join(", ")}. Это даты получения архива, а не даты всех измерений.</p>}
            {wells.data.density_default && <p className="muted">Плотность объекта: {wells.data.density_default.density_kgm3} кг/м³. Получена {wells.data.density_default.available_from}; источник: {wells.data.density_default.source}. Это значение объекта, а не замена измерениям плотности в ГДИ.</p>}
            {history.data.warnings.map((warning, index) => <p key={index} className="notice">{warning}</p>)}
          </details>
          {pressureSeries.length > 0 ? <section aria-label="Месячные давления скважины">
            <h3>Давление на устье и на БГ по месяцам</h3>
            <p className="muted">Месячные фактические записи, атм. Линии соединяют записи, пропуски не восстанавливаются. {objectId !== "demo-ppd" && "Нулевые записи могут означать отсутствие измерения; месяц выгрузки может быть неполным."}</p>
            <Plot title="Месячные давления скважины" data={pressureSeries} layout={{ timeGranularity: "month", xaxis: { type: "date" }, yaxis: { title: { text: "атм" } } }} />
          </section> : <p className="notice">Месячных фактических давлений для графика нет.</p>}
          <section aria-label="Архивный текущий режим"><h3>Текущий режим по архиву</h3>
            {objectId !== "demo-ppd" && <p className="muted">Дата режима указана по выгрузке; дата самого измерения не подтверждена.</p>}
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
