import { Table } from "../../shared/ui/Table";
import { fmt } from "../../shared/ui/format";
import type { Defects, MotorBenchmark, PumpBenchmark } from "./types";

export function Benchmarks({ pump, motor }: { pump?: PumpBenchmark | null; motor?: MotorBenchmark | null }) {
  if (!pump && !motor) return null;
  return <section aria-label="Бенчмарки">
    <h3>Сравнение с бенчмарками</h3>
    {pump && <Table rows={[
      { name: "Класс подачи КНС", current: `${pump.class} ${pump.flow_unit} (агрегат: ${fmt(pump.daily_flow_m3, 0)})`, best: "" },
      { name: "Типоразмер", current: pump.current_pumps, best: pump.efficient_pumps },
      { name: "Средневзвешенный УРЭ, кВт·ч/м³", current: pump.current_sec, best: pump.efficient_sec },
      { name: "КПД, %", current: pump.current_efficiency, best: pump.efficient_efficiency },
      { name: "УРЭ агрегата факт, кВт·ч/м³", current: pump.sec_fact, best: "" },
    ]} columns={[
      { key: "name", label: "Насосы" },
      { key: "current", label: "Применяемые", align: "start" },
      { key: "best", label: "Энергоэффективные", align: "start" },
    ]} />}
    {motor && <Table rows={[
      { name: "Позиция бенчмарка", current: `${motor.item} · ${motor.group}`, best: "" },
      { name: "Марка", current: motor.current_brand, best: motor.best_brand },
      { name: "Аналоги", current: motor.alternatives.join("; "), best: "" },
      { name: "КПД, %", current: motor.current_efficiency_pct, best: motor.best_efficiency_pct },
      { name: "КПД паспорта агрегата, %", current: motor.passport_efficiency_pct, best: motor.gain_pct !== null ? `+${fmt(Math.max(motor.gain_pct, 0), 1)} п.п. у НДТ` : "" },
    ]} columns={[
      { key: "name", label: `Электродвигатель ${fmt(motor.power_kw, 0)} кВт` },
      { key: "current", label: "Применяемый", align: "start" },
      { key: "best", label: "НДТ", align: "start" },
    ]} />}
  </section>;
}

export function DefectHistory({ defects }: { defects?: Defects | null }) {
  if (!defects) return null;
  return <section aria-label="Дефекты по 1С ТОИР">
    <h3>Дефекты по журналу 1С ТОИР</h3>
    <p className="muted">{defects.element} · записей {defects.total}, из них высокой критичности {defects.high} · {defects.first ?? "—"} — {defects.last ?? "—"}</p>
    <Table rows={defects.by_kind.map(kind => ({
      kind: kind.kind, count: kind.count, last: kind.last,
      causes: kind.algorithm.map(row => `${row.cause} → ${row.action}`).join("; ") || "—",
    }))} columns={[
      { key: "kind", label: "Вид дефекта" },
      { key: "count", label: "Случаев", digits: 0 },
      { key: "last", label: "Последний", align: "start" },
      { key: "causes", label: "Вероятные причины и меры (алгоритм НА)", align: "start" },
    ]} />
    <details><summary>Последние записи журнала</summary>
      <Table rows={defects.recent} columns={[
        { key: "date", label: "Дата", align: "start" },
        { key: "defect", label: "Дефект", align: "start" },
        { key: "cause", label: "Причина", align: "start" },
        { key: "criticality", label: "Критичность", align: "start" },
        { key: "status", label: "Статус", align: "start" },
      ]} />
    </details>
  </section>;
}
