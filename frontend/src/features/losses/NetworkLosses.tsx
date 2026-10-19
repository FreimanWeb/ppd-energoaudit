import { useState, type FormEvent } from "react";
import type { OperatorBalance } from "../scheme/LossFlow";
import { chainLossGroups } from "../../pages/lossChartData.mjs";
import type { Audit } from "../../shared/types";
import { segment, useResource } from "../../shared/api";
import { Button, LinkButton } from "../../shared/ui/Button";
import { Panel } from "../../shared/ui/Panel";
import { Status } from "../../shared/ui/Status";
import { Table } from "../../shared/ui/Table";
import { fmt } from "../../shared/ui/format";
import { LossCharts, type Loss } from "./LossCharts";
import { networkMeasures } from "./networkScenario.mjs";
import { networkStages,stageDefinitions } from "./networkStages.mjs";
import "./networkLosses.css";

type Provenance = "calculated" | "synthetic" | "measured";
const origins: Record<Provenance, string> = { calculated: "Рассчитано", synthetic: "Синтетика", measured: "Измерено" };
const axisLabels: Record<string, string> = {
  "Подведённая мощность": "Ввод",
  "Потери ПЧ": "ПЧ",
  "Потери ЭД": "ЭД",
  "Потери передачи": "Передача",
  "Потери насоса": "Насос",
  "Гидравлика насос→БГ": "До БГ",
  "Гидравлическая мощность на БГ": "Мощность на БГ",
  "Трение в трубопроводах": "Трубы",
  "Арматура сети и скважин": "Арматура",
  "Трение в стволах скважин": "НКТ",
  "Штуцирование скважин": "Штуцеры",
  "Полезная мощность": "Закачка",
  "Полезная закачка": "Закачка",
  "Номинальные потери НА": "Номинальные",
  "Потери из-за снижения КПД": "Снижение КПД",
  "Отклонение от номинального КПД": "Отклонение КПД",
  "Потери на участке Насос–БГ": "Насос–БГ",
  "Потери в трубопроводах": "Трубопроводы",
  "Штуцирование нагнетательных скважин": "Штуцирование",
  "Гидравлическая мощность на устьях": "На устьях",
};
const parameters = [
  { key: "roughness_mm", label: "Шероховатость труб, мм", value: 0.1, min: 0, max: 5, step: 0.01 },
  { key: "well_depth_m", label: "Длина ствола скважины, м", value: 1800, min: 1, max: 10000, step: 1 },
  { key: "well_diameter_mm", label: "Внутренний диаметр НКТ, мм", value: 62, min: 10, max: 500, step: 1 },
  { key: "local_resistance_k", label: "Коэффициент местных сопротивлений", value: 2, min: 0, max: 1000, step: 0.1 },
  { key: "useful_pressure_mpa", label: "Требуемое полезное давление без перепада высот, МПа", value: 3, min: 0, max: 100, step: 0.1 },
  { key: "elevation_change_m", label: "Перепад высот от станции к скважинам, м", value: 0, min: -1000, max: 1000, step: 1 },
] as const;
type Scenario = Record<(typeof parameters)[number]["key"], number>;
type Intervention = "reduce_head" | "clean_pipes" | "reduce_local_resistance";
type NetworkMeasure = { id: Intervention; name: string; loss_name: string; description: string; saving_kw: number; saving_pct: number; baseline_input_kw: number; after_input_kw: number; required_pressure_mpa: number; options: Record<string, number>; assumptions: string[] };
type NetworkPower = { input_kw: number; total_loss_kw: number; useful_kw: number };
type NetworkResponse = {
  status: "scenario" | "infeasible";
  title: string;
  input_kw: number;
  useful_kw: number | null;
  operator_balance?: OperatorBalance|null;
  total_loss_kw: number | null;
  balance_error_kw: number | null;
  items: (Loss & { provenance: Provenance; basis: string })[];
  segments: { id: string; pipeline_id: string; name: string; length_m: number; inner_diameter_mm: number; flow_m3h: number; pressure_loss_mpa: number; power_kw: number; provenance: Provenance; basis: string; source_sheet: string; source_row: number }[];
  wells: { id: string; flow_m3h: number; pipe_loss_kw: number; well_loss_kw: number; armature_loss_kw: number; choke_loss_kw: number | null; useful_kw: number; required_pressure_mpa: number; available_pressure_mpa: number; deficit_mpa: number; deficit_kw: number; synthetic_connection: boolean }[];
  assumptions: { parameter: string; label: string; value: number | string | null; unit: string; provenance: Provenance; basis: string }[];
  warnings: string[];
  network: { pipeline_count: number; segment_count: number; well_count: number; total_length_m?: number; source_file: string; exported_at: string };
  runtime_reading?: { hours: number; as_of: string; basis: string } | null;
  measures?: NetworkMeasure[];
  comparison?: { measure_id: Intervention; name: string; saving_kw: number; saving_pct: number; before: NetworkPower; after: NetworkPower & { balance_error_kw: number; items: Loss[] }; assumptions: string[] } | null;
} | { status: "unavailable"; warnings: string[]; measures?: NetworkMeasure[]; runtime_reading?: { hours: number; as_of: string; basis: string } | null };

export function NetworkLosses({ audit, view = "map" }: { audit: Audit; view?: "map" | "scenario" }) {
  const editable = view === "scenario";
  const [scenario, setScenario] = useState<Scenario>(() => Object.fromEntries(parameters.map(p => [p.key, p.value])) as Scenario);
  const [mode, setMode] = useState<"decomposition" | "percentage">("decomposition");
  const [detailed,setDetailed]=useState(false);
  const [selectedName, setSelectedName] = useState("");
  const [intervention, setIntervention] = useState<Intervention | null>(null);
  const demo = audit.audit.object_id === "demo-ppd";
  const timestamp = audit.snapshot?.timestamp;
  const resource = useResource<NetworkResponse>(
    audit.source === "field_trip" || timestamp
      ? `/objects/${segment(audit.audit.object_id)}/aggregates/${segment(audit.audit.aggregate_id)}/network-losses` : null,
    JSON.stringify({ source: audit.source, ...(audit.source === "telemetry" && timestamp ? { day: timestamp.slice(0, 10), timestamp } : {}), ...(editable ? {scenario, intervention} : {}) }),
  );
  const data = resource.data;
  const bgPower=data?.status === "scenario" ? data.operator_balance?.bg_kw : undefined;
  const physicalItems=data && data.status !== "unavailable" ? data.items.flatMap(item=>
    item.name === "Гидравлика насос→БГ" && typeof bgPower === "number" && Number.isFinite(bgPower)
      ? [item,{name:"Гидравлическая мощность на БГ",power_kw:bgPower,share:bgPower/data.input_kw,category:"промежуточная"}]
      : [item]) : [];
  const balance=data?.status === "scenario" ? data.operator_balance : null;
  const summaryItems=chainLossGroups(balance);
  const grouped=!editable && !detailed && summaryItems.length>0;
  const chartItems=grouped ? summaryItems : physicalItems;
  const groups=grouped && balance ? [
    {id:"hall",label:"Машинный блок",names:balance.groups.find(group=>group.id === "hall")!.children.map(child=>child.name)},
    {id:"pipes",label:"Трубопроводы",names:["Потери в трубопроводах"]},
    {id:"wells",label:"Скважины и арматура",names:["Штуцирование нагнетательных скважин"]},
  ] : stageDefinitions.map(stage=>({...stage,label:stage.id === "hall" ? "Машинный блок" : stage.label}));
  const stages=grouped && balance ? balance.groups.map(group=>({id:group.id,label:groups.find(stage=>stage.id === group.id)!.label,power_kw:group.power_kw,share_pct:group.power_kw/balance.input_kw*100})) : networkStages(data);
  const selected = data && data.status !== "unavailable" ? data.items.find(item => item.name === selectedName) : undefined;
  const measures = networkMeasures(data?.status ?? "", data?.measures ?? [], selectedName);
  const comparison = data?.status === "scenario" && data.comparison?.measure_id === intervention ? data.comparison : null;
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setScenario(Object.fromEntries(parameters.map(p => [p.key, Number(form.get(p.key))])) as Scenario);
    setIntervention(null);
    setSelectedName("");
  };
  return <Panel title={editable ? "Гидравлический сценарий" : "Карта потерь по цепочке"} action={!editable ? <LinkButton href="#network-scenario">Гидравлический сценарий</LinkButton> : undefined}>
    <div className="network-losses">
      {editable && <p className="notice">{demo ? "Демонстрационный объект: геометрия, режимы и потери синтетические. Не производственные данные." : "Геометрия — из АРМИТС; единицы выгрузки ещё требуют подтверждения. Недостающие параметры и распределение потока заменены синтетикой. Это сценарная оценка, а не измеренные потери или достигнутая экономия."}</p>}
      {editable && <details className="network-scenario">
        <summary>Параметры сценария</summary>
        <form onSubmit={submit}>
          <div className="network-scenario-fields">{parameters.map(p => <label key={p.key}>
            <span>{p.label}</span>
            <input name={p.key} type="number" required min={p.min} max={p.max} step={p.step} defaultValue={scenario[p.key]} />
            <small>Синтетическое значение</small>
          </label>)}</div>
          <p className="muted">Полезное давление задано в поверхностном эквиваленте без перепада высот; высоты учитываются отдельно. Положительный перепад — подъём от станции. Длина ствола используется только для расчёта трения.</p>
          <Button type="submit" loading={resource.loading}>Пересчитать сценарий</Button>
        </form>
      </details>}
      <Status {...resource} empty="Для расчёта выберите режим агрегата." />
      {intervention && !data && <Button variant="secondary" onClick={() => setIntervention(null)}>Вернуться к исходному сценарию</Button>}
      {data && <>
        {data.status !== "unavailable" && <>
          <p className="muted">{data.title}</p>
          <p className="network-metadata">{data.network.well_count} скважин · {fmt((data.network.total_length_m ?? [...new Map(data.segments.map(item => [item.id, item])).values()].reduce((sum, item) => sum + item.length_m, 0)) / 1000, 1)} км учтённых участков · перепад высот {fmt(scenario.elevation_change_m, 0)} м (синтетика). {demo ? "Геометрия синтетическая, длины в метрах и диаметры в миллиметрах." : "Геометрия по реестру, единицы не подтверждены."}</p>
        </>}
        {data.warnings.length > 0 && (data.status === "unavailable"
          ? <div className="notice" role="status"><ul>{data.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>
          : <details><summary>Ограничения и принятые соединения ({data.warnings.length})</summary><ul>{data.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>)}
        {data.status === "unavailable" ? <p className="notice error" role="alert">Карта всей цепочки недоступна для выбранного режима.</p> : <>
        {data.status === "scenario" ? <>
          <dl className="network-balance-totals">
            <div><dt>Подведённая мощность</dt><dd>{fmt(data.input_kw)} кВт</dd></div>
            <div><dt>Гидравлическая мощность на БГ</dt><dd>{fmt(bgPower)} кВт</dd></div>
            <div><dt>Потери всей цепочки</dt><dd>{fmt(grouped ? balance?.total_loss_kw : data.total_loss_kw)} кВт</dd></div>
            <div><dt>{grouped ? "На устьях после штуцеров" : "Полезная мощность"}</dt><dd>{fmt(grouped ? balance?.output_kw : data.useful_kw)} кВт</dd></div>
            <div><dt>Невязка баланса</dt><dd>{fmt(grouped && balance ? balance.input_kw-balance.total_loss_kw-balance.output_kw : data.balance_error_kw !== null && Math.abs(data.balance_error_kw) < 1e-9 ? 0 : data.balance_error_kw, 3)} кВт</dd></div>
          </dl>
          <dl className="network-balance-totals" aria-label="Потери по участкам цепочки">
            {stages.map(stage => <div key={stage.id}><dt>{stage.label}</dt><dd>{fmt(stage.power_kw)} кВт · {fmt(stage.share_pct,1)} % {grouped ? "потребления" : "потерь"}</dd></div>)}
          </dl>
          <div className="metric-toolbar"><div className="metric-segments" role="group" aria-label="Представление всей цепочки">
            <button type="button" aria-pressed={mode === "decomposition"} onClick={() => setMode("decomposition")}>Разложение</button>
            <button type="button" aria-pressed={mode === "percentage"} onClick={() => setMode("percentage")}>Структура, %</button>
          </div>
            {!editable && summaryItems.length>0 && <Button variant="secondary" aria-expanded={detailed} onClick={()=>{setDetailed(previous=>!previous);setSelectedName("");}}>{detailed ? "Свернуть детализацию" : "Детализация"}</Button>}
          </div>
          <p className="stage-basis">{grouped ? "Граница расчёта — устья после штуцеров. Трение в НКТ доступно в детализации." : "Подробный баланс включает трение в стволах скважин до полезной закачки."}</p>
          {mode === "decomposition" ? <>
            <div className="network-waterfall-scroll" tabIndex={0} role="region" aria-label="Разложение всей цепочки, горизонтальная прокрутка">
              <div className="network-waterfall-wide"><LossCharts power={data.input_kw} losses={chartItems} mode={mode} showSummary={false} axisLabels={axisLabels} groups={groups} onSelect={setSelectedName} /></div>
            </div>
            <p className="muted network-waterfall-hint">На узком экране прокрутите график вправо; доступны стрелки клавиатуры.</p>
          </> : <LossCharts power={data.input_kw} losses={chartItems} mode={mode} showSummary={false} onSelect={setSelectedName} />}
          {editable ? <><section className="network-actions" aria-label="Мероприятия всей цепочки">
            <div className="network-section-heading">
              <h3>{selected ? "Мероприятия по выбранной составляющей" : "Приоритетные мероприятия"}</h3>
              {selectedName && <Button variant="secondary" onClick={() => setSelectedName("")}>Все мероприятия</Button>}
            </div>
            {selected ? <p><strong>{selected.name}: {fmt(selected.power_kw)} кВт.</strong> {selected.basis} Происхождение: {origins[selected.provenance]}.</p>
              : <p className="muted">Выберите составляющую на графике для разбора. Мероприятия упорядочены по сценарному снижению подведённой мощности при прежней закачке.</p>}
            <p className="muted">Это альтернативные сценарии от одного исходного режима. Экономию разных мероприятий нельзя складывать.</p>
            {measures.length ? <div className="network-measures">{measures.map(measure => <article className="network-measure" key={measure.id}>
              <h4>{measure.name}</h4>
              <p>{measure.description}</p>
              <p className="network-measure-saving">Прогноз: −{fmt(measure.saving_kw)} кВт · {fmt(measure.saving_pct, 1)}% ввода</p>
              <p className="muted">Составляющая: {measure.loss_name}. Требуемое давление: {fmt(measure.required_pressure_mpa, 2)} МПа.</p>
              <details><summary>Условия оценки</summary><ul>{measure.assumptions.map((assumption, index) => <li key={index}>{assumption}</li>)}</ul></details>
              <Button variant={intervention === measure.id ? "secondary" : "primary"} loading={resource.loading} onClick={() => setIntervention(measure.id)}>Оценить сценарий</Button>
            </article>)}</div> : <p className="notice">{selected
              ? "Для этой составляющей пока нет применимого мероприятия в модели. Показанная мощность не означает, что её можно устранить целиком."
              : "При заданных параметрах модель не нашла применимых мероприятий со снижением мощности."}</p>}
          </section>
          {comparison && <section className="network-comparison" aria-label="Результат мероприятия">
            <div className="network-section-heading"><h3>Сценарий: {comparison.name}</h3><Button variant="secondary" onClick={() => setIntervention(null)}>Вернуться к исходному сценарию</Button></div>
            <p className="network-measure-saving">Прогнозируемое снижение мощности: {fmt(comparison.saving_kw)} кВт ({fmt(comparison.saving_pct, 1)}%).</p>
            <p className="notice">Расчётный сценарий при неизменных расходе и полезной задаче. Это прогноз модели, не достигнутая экономия.</p>
            <Table rows={[
              { name: "Подведённая мощность", before: comparison.before.input_kw, after: comparison.after.input_kw },
              { name: "Потери всей цепочки", before: comparison.before.total_loss_kw, after: comparison.after.total_loss_kw },
              { name: "Полезная мощность", before: comparison.before.useful_kw, after: comparison.after.useful_kw },
            ]} columns={[{ key: "name", label: "Показатель" }, { key: "before", label: "До, кВт" }, { key: "after", label: "После, кВт" }]} />
            <p className="muted">Невязка после: {fmt(Math.abs(comparison.after.balance_error_kw) < 1e-9 ? 0 : comparison.after.balance_error_kw, 3)} кВт.</p>
            <ul>{comparison.assumptions.map((assumption, index) => <li key={index}>{assumption}</li>)}</ul>
          </section>}
          {intervention && !comparison && <p className="notice">Сравнение для выбранного мероприятия недоступно. <Button variant="secondary" onClick={() => setIntervention(null)}>Вернуться к исходному сценарию</Button></p>}
          </> : selected && <p><strong>{selected.name}: {fmt(selected.power_kw)} кВт.</strong> {selected.basis} Происхождение: {origins[selected.provenance]}.</p>}
        </> : <p className="notice error" role="alert">{data.status === "infeasible" ? "Сценарий физически невыполним: доступного давления недостаточно. Сбалансированная карта не построена." : "Карта всей цепочки недоступна для выбранного режима."}</p>}
        {editable && <>
        {data.items.length > 0 && <details><summary>Составляющие и основания расчёта</summary><Table rows={data.items.map(item => ({ ...item, origin: origins[item.provenance], percent: item.share * 100 }))} columns={[
          { key: "name", label: "Составляющая" }, { key: "power_kw", label: "Мощность, кВт" }, { key: "percent", label: "Доля, %" }, { key: "origin", label: "Происхождение" }, { key: "basis", label: "Основание" },
        ]} /></details>}
        <details><summary>Трубопроводы: {data.network.pipeline_count} · участки: {data.network.segment_count}</summary>
          <p className="muted">Общие участки учитываются один раз. В сценарии работает только выбранный агрегат: его расход распределяется по всей сети, остальные насосы выключены. Это не оценка его вклада при совместной работе агрегатов.</p>
          <Table rows={data.segments.map(row => ({ ...row, origin: origins[row.provenance], source: `${row.source_sheet}, строка ${row.source_row}` }))} columns={[
            { key: "pipeline_id", label: "Трубопровод" }, { key: "name", label: "Участок" }, { key: "length_m", label: "Длина, м" }, { key: "inner_diameter_mm", label: "Внутренний диаметр, мм" }, { key: "flow_m3h", label: "Расход, м³/ч" }, { key: "pressure_loss_mpa", label: "Потери давления, МПа", digits: 3 }, { key: "power_kw", label: "Потери, кВт" }, { key: "origin", label: "Происхождение" }, { key: "source", label: "Источник геометрии" },
          ]} />
        </details>
        <details open={data.status === "infeasible"}><summary>Скважины: {data.network.well_count}</summary>
          <Table rows={data.wells.map(row => ({ ...row, connection: row.synthetic_connection ? "Синтетическая" : "По реестру" }))} rowHighlighted={row => Number(row.deficit_kw) > 0} columns={[
            { key: "id", label: "Скважина" }, { key: "flow_m3h", label: "Расход, м³/ч" }, { key: "pipe_loss_kw", label: "Трубы по пути, кВт" }, { key: "well_loss_kw", label: "Трение в стволе, кВт" }, { key: "armature_loss_kw", label: "Арматура, кВт" }, { key: "choke_loss_kw", label: "Дросселирование, кВт" }, { key: "useful_kw", label: "Полезная мощность, кВт" }, { key: "required_pressure_mpa", label: "Требуется, МПа" }, { key: "available_pressure_mpa", label: "Доступно, МПа" }, { key: "deficit_mpa", label: "Дефицит, МПа" }, { key: "deficit_kw", label: "Дефицит, кВт" }, { key: "connection", label: "Связь с сетью" },
          ]} />
          <p className="muted">Потери труб по пути к скважинам могут включать общие участки: этот столбец нельзя суммировать. Итог сети рассчитан по уникальным участкам.</p>
        </details>
        <details><summary>Исходные данные и допущения</summary><Table rows={data.assumptions.map(row => ({ ...row, origin: origins[row.provenance] }))} columns={[
          { key: "label", label: "Параметр" }, { key: "value", label: "Значение" }, { key: "unit", label: "Единица" }, { key: "origin", label: "Происхождение" }, { key: "basis", label: "Основание" },
        ]} /></details>
        <p className="muted">Источник сети: {data.network.source_file} · выгрузка {data.network.exported_at}.</p>
        </>}
        </>}
        {editable && data.runtime_reading && <p className="notice">Накопленная наработка {audit.audit.aggregate_id}: {fmt(data.runtime_reading.hours, 0)} ч, на {data.runtime_reading.as_of}. {data.runtime_reading.basis}</p>}
      </>}
    </div>
  </Panel>;
}
