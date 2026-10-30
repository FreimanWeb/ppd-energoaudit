import { segment, useResource } from "../shared/api";
import { Status } from "../shared/ui/Status";
import { Table, type TableColumn } from "../shared/ui/Table";

type AcceptanceSignal = {
  metric: string;
  unit: string;
  records: number;
  valid: number;
  first: string | null;
  last: string | null;
  days: number;
  max_gap_hours: number | null;
  issues: string[];
};

type AcceptanceCalculation = {
  name: string;
  status: "available" | "blocked";
  reason: string;
};

type AcceptanceReport = {
  signals: AcceptanceSignal[];
  calculations: AcceptanceCalculation[];
  note: string;
};

/** Отображаемые имена метрик телеметрии (как в рядах и карточке источников). */
const signalNames: Record<string, string> = {
  density: "Плотность",
  energy: "Энергия за сутки (W_сут)",
  flow_rate: "Мгновенная подача (Q)",
  p_bg: "Давление на гребёнке (p_БГ)",
  p_in: "Давление на приёме (p_вх)",
  p_out: "Давление на выкиде (p_вых)",
  power: "Электрическая мощность (P_эл)",
  pump_state: "Состояние агрегата",
  q_day: "Суточный объём (Q_сут)",
  runtime: "Наработка за сутки (T_сут)",
  viscosity: "Вязкость",
};

const dateFormat = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const signalColumns: TableColumn[] = [
  { key: "name", label: "Сигнал", align: "start" },
  { key: "unit", label: "Единицы", align: "start" },
  { key: "valid", label: "Валидные / всего", align: "end" },
  { key: "first", label: "Первая запись", align: "start", render: (row) => (row.first ? dateFormat.format(new Date(row.first as string)) : "—") },
  { key: "last", label: "Последняя запись", align: "start", render: (row) => (row.last ? dateFormat.format(new Date(row.last as string)) : "—") },
  { key: "days", label: "Суток с данными", align: "end", digits: 0 },
  { key: "max_gap_hours", label: "Макс. интервал, ч", align: "end", digits: 1 },
  { key: "issues", label: "Замечания", align: "start" },
];

function AcceptanceView({ report }: { report: AcceptanceReport }) {
  const signals = report.signals;
  const calculations = report.calculations;
  const missing = signals.filter((signal) => signal.records === 0);
  const invalid = signals.filter((signal) => signal.records > 0 && signal.valid === 0);
  const blocked = calculations.filter((calculation) => calculation.status === "blocked");
  const available = calculations.filter((calculation) => calculation.status !== "blocked");
  const rows = signals.map((signal) => ({
    ...signal,
    name: signalNames[signal.metric] ?? signal.metric,
    valid: `${signal.valid} / ${signal.records}`,
    issues: signal.issues.join("; "),
  }));
  return (
    <>
      <details><summary>Границы проверки</summary><p className="muted">{report.note}</p></details>
      {missing.length > 0 && (
        <p role="status">
          Нет записей по сигналам: {missing.map((signal) => signalNames[signal.metric] ?? signal.metric).join(", ")}.
        </p>
      )}
      {invalid.length > 0 && (
        <p role="status">
          Записи есть, но валидных значений нет: {invalid.map((signal) => signalNames[signal.metric] ?? signal.metric).join(", ")}.
        </p>
      )}
      {calculations.length > 0 && (
        <>
          <h4>Расчёты по полноте исходных данных</h4>
          <p className="muted">
            «Доступен» означает только наличие исходных сигналов хотя бы за одни сутки или момент
            периода — не полное покрытие периода и не готовый расчёт.
          </p>
          {available.map((calculation) => (
            <p key={calculation.name}>
              Входные данные есть — {calculation.name}: {calculation.reason}
            </p>
          ))}
          {blocked.map((calculation) => (
            <p role="status" key={calculation.name}>
              {calculation.name}: недоступен — {calculation.reason}
            </p>
          ))}
        </>
      )}
      {signals.length > 0 ? (
        <details>
          <summary>Сигналы телеметрии ({signals.length})</summary>
          <p className="muted">
            Первая и последняя записи, сутки с данными и максимальный интервал посчитаны по валидным
            записям. Периодичность поступления не задана, поэтому доля покрытия не оценивается —
            показан только наблюдаемый интервал.
          </p>
          <Table rows={rows} columns={signalColumns} />
        </details>
      ) : (
        <p>Сервис не вернул ни одного ожидаемого сигнала за выбранный период.</p>
      )}
    </>
  );
}

/** Приёмка телеметрии: полнота исходных сигналов за тот же период, что и графики. */
export function TelemetryAcceptance({
  objectId,
  aggregateId,
  from,
  to,
}: {
  objectId: string;
  aggregateId: string;
  from: string;
  to: string;
}) {
  const report = useResource<AcceptanceReport>(
    objectId && aggregateId && from && to && from <= to
      ? `/objects/${segment(objectId)}/telemetry-acceptance?aggregate_id=${segment(aggregateId)}&start=${from}&end=${to}`
      : null,
  );
  if (!objectId || !aggregateId || !from || !to || from > to) return null;
  return (
    <section aria-label="Приёмка данных">
      <h3>Приёмка данных</h3>
      <Status {...report} empty="Сервис не вернул отчёт о приёмке данных." />
      {report.data && <AcceptanceView report={report.data} />}
    </section>
  );
}
