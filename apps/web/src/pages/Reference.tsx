import { useResource } from "../shared/api";
import { Panel } from "../shared/ui/Panel";
import { Status } from "../shared/ui/Status";
import { Table } from "../shared/ui/Table";
import { fmt } from "../shared/ui/format";
import type { AlgorithmRow } from "../features/recommendations/types";
import "../features/recommendations/recommendations.css";

type Rule = { id: string; label: string; value_mm: number; range_mm: [number, number]; sources: string[] };
type Efficiency = { text: string };
type Reference = {
  hydraulics: { roughness: Rule[]; tubing: Rule };
  diagnostic_rules: {
    source: { artifact_id: string; file: string; sha256: string };
    rules: { id: string; title: string; category: string; condition: string; action: string; confirmation: string }[];
    bindings: { object_id: string; aggregate_id: string; model: string; sheet: string; flow_min: number; flow_max: number; note: string }[];
  };
  pump_benchmark: { system: string; objects: string; flow_unit: string; sec_unit: string; rows: { class: string; current_pumps: string; current_sec: number; current_efficiency: Efficiency; efficient_pumps: string; efficient_sec: number; efficient_efficiency: Efficiency }[] }[];
  motor_benchmark: { id: string; type: string; items: { id: string; brands: Record<string, string>; power_kw: number; speed_rpm: number[]; efficiency: Record<string, Efficiency>; objects?: string }[] }[];
  critical_parameters: { title: string; approved_by: string; rows: AlgorithmRow[]; pump_ranges: Record<string, number | string | null>[]; pump_range_notes: string[] };
};

const categories: Record<string, string> = {
  data_check: "Проверка исходных данных",
  operating_deviation: "Отклонение режима",
  inspection: "Основание для обследования",
};

export function ReferencePage() {
  const resource = useResource<Reference>("/reference");
  const data = resource.data;
  return <Panel title="Справочные материалы">
    <Status {...resource} />
    {data && <>
      <details className="reference-section" open><summary>Шероховатость труб для гидравлического расчёта</summary>
        <p className="muted">В реестре трубопроводов шероховатости нет. Значение выбирается по типу трубы, материалу и внутреннему покрытию участка; правила применяются сверху вниз.</p>
        <Table rows={[...data.hydraulics.roughness, data.hydraulics.tubing].map(rule => ({
          label: rule.label, value: rule.value_mm, range: `${fmt(rule.range_mm[0], 3)}–${fmt(rule.range_mm[1], 3)}`,
        }))} columns={[
          { key: "label", label: "Труба" }, { key: "value", label: "Принято Δэ, мм", digits: 3 },
          { key: "range", label: "Диапазон, мм", align: "end" },
        ]} />
        <ul className="reference-sources">{[...new Set(data.hydraulics.roughness.flatMap(rule => rule.sources))].map(source => <li key={source}>{source}</li>)}</ul>
      </details>
      <details className="reference-section"><summary>Правила адресной диагностики насосного агрегата</summary>
        <p className="muted">{data.diagnostic_rules.source.artifact_id} · {data.diagnostic_rules.source.file}. Правила применяются только к агрегату с той же моделью насоса; рабочие области и кривые требуют сверки с паспортом.</p>
        <Table rows={data.diagnostic_rules.rules.map(rule => ({ ...rule, category: categories[rule.category] ?? rule.category, note: rule.action || rule.confirmation }))} columns={[
          { key: "title", label: "Правило" }, { key: "category", label: "Вид", align: "start" },
          { key: "condition", label: "Условие", align: "start" }, { key: "note", label: "Действие или ограничение", align: "start" },
        ]} />
        <Table rows={data.diagnostic_rules.bindings.map(item => ({ ...item, range: `${fmt(item.flow_min, 0)}–${fmt(item.flow_max, 0)}` }))} columns={[
          { key: "object_id", label: "Объект" }, { key: "aggregate_id", label: "Агрегат" }, { key: "model", label: "Модель", align: "start" },
          { key: "range", label: "Рабочая область, м³/ч", align: "end" }, { key: "note", label: "Примечание", align: "start" },
        ]} />
      </details>
      <details className="reference-section"><summary>Бенчмаркинг насосов</summary>
        {data.pump_benchmark.map(block => <section key={block.system}>
          <h4>{block.system} · {block.objects}</h4>
          <Table rows={block.rows.map(row => ({ ...row, current_eff: row.current_efficiency.text, efficient_eff: row.efficient_efficiency.text }))} columns={[
            { key: "class", label: `Подача, ${block.flow_unit}` },
            { key: "current_pumps", label: "Применяемые", align: "start" },
            { key: "current_sec", label: `УРЭ, ${block.sec_unit}`, digits: 2 },
            { key: "current_eff", label: "КПД, %", align: "end" },
            { key: "efficient_pumps", label: "Энергоэффективные", align: "start" },
            { key: "efficient_sec", label: `УРЭ, ${block.sec_unit}`, digits: 2 },
            { key: "efficient_eff", label: "КПД, %", align: "end" },
          ]} />
        </section>)}
      </details>
      <details className="reference-section"><summary>Бенчмаркинг электродвигателей</summary>
        {data.motor_benchmark.map(group => <section key={group.id}>
          <h4>{group.id}. {group.type}</h4>
          <Table rows={group.items.map(item => ({
            id: item.id, power: item.power_kw, speed: item.speed_rpm?.[0] ?? null,
            current: item.brands.current, best: item.brands.best,
            eff: `${item.efficiency?.current?.text ?? "—"} → ${item.efficiency?.best?.text ?? "—"}`,
          }))} columns={[
            { key: "id", label: "№" }, { key: "power", label: "P, кВт", digits: 0 }, { key: "speed", label: "n, об/мин", digits: 0 },
            { key: "current", label: "Применяемый", align: "start" }, { key: "best", label: "НДТ", align: "start" },
            { key: "eff", label: "КПД, % (прим. → НДТ)", align: "end" },
          ]} />
        </section>)}
      </details>
      <details className="reference-section"><summary>Алгоритм определения критичных параметров НА</summary>
        <p className="muted">{data.critical_parameters.title}. {data.critical_parameters.approved_by}</p>
        <Table rows={data.critical_parameters.rows} columns={[
          { key: "id", label: "№", digits: 0 }, { key: "deviation", label: "Отклонение", align: "start" },
          { key: "cause", label: "Вероятная причина", align: "start" }, { key: "action", label: "Меры", align: "start" },
          { key: "responsible", label: "Исполнитель", align: "start" },
        ]} />
      </details>
      <details className="reference-section"><summary>Рабочие характеристики насосов ЦНСн</summary>
        <Table rows={data.critical_parameters.pump_ranges} columns={[
          { key: "size", label: "Типоразмер" }, { key: "head_m", label: "Напор, м", digits: 0 },
          { key: "q_min_m3h", label: "Q мин, м³/ч", digits: 0 }, { key: "q_max_m3h", label: "Q макс, м³/ч", digits: 0 },
          { key: "p_in_min_atm", label: "p_пр мин, атм", digits: 1 }, { key: "p_in_max_atm", label: "p_пр макс, атм", digits: 1 },
          { key: "p_out_min_atm", label: "p_вых мин, атм", digits: 1 }, { key: "p_out_max_atm", label: "p_вых макс, атм", digits: 1 },
        ]} />
        <ul className="reference-sources">{data.critical_parameters.pump_range_notes.map(note => <li key={note}>{note}</li>)}</ul>
      </details>
    </>}
  </Panel>;
}
