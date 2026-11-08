import type { DiagnosticReport, DiagnosticRule } from "../../shared/types";
import { Panel } from "../../shared/ui/Panel";
import { Table } from "../../shared/ui/Table";
import "./diagnostics.css";

const statuses: Record<DiagnosticRule["status"], string> = {
  triggered: "Признак для проверки",
  clear: "Условие не обнаружено",
  insufficient_data: "Недостаточно данных",
  pending_confirmation: "Требует подтверждения",
  not_applicable: "Не применяется",
};
const categories: Record<DiagnosticRule["category"], string> = {
  data_check: "Проверка исходных данных",
  operating_deviation: "Отклонения режима",
  inspection: "Основания для обследования",
};

function Rule({ rule }: { rule: DiagnosticRule }) {
  return <article className="diagnostic-rule" data-status={rule.status}>
    <div className="diagnostic-heading">
      <h4>{rule.title}</h4>
      <span className="diagnostic-status">{statuses[rule.status]}</span>
    </div>
    <p>{rule.action || rule.reason}</p>
    <details>
      <summary>Условие, значения и источник</summary>
      <p><strong>Условие:</strong> {rule.condition}</p>
      {rule.action && <p>{rule.reason}</p>}
      <Table rows={rule.evidence.map(item => ({ ...item }))} columns={[
        { key: "label", label: "Параметр" },
        { key: "value", label: "Значение", digits: 4 },
        { key: "unit", label: "Единица" },
        { key: "basis", label: "Основание" },
      ]} />
      <p className="muted diagnostic-source">Источник: {rule.source.artifact_id} · {rule.source.file}<br />
        Лист «{rule.source.sheet}» · {rule.source.cells}<br />
        SHA-256: <code>{rule.source.sha256}</code>
      </p>
    </details>
  </article>;
}

export function Diagnostics({ report }: { report: DiagnosticReport }) {
  const triggered = report.rules.filter(rule => rule.status === "triggered");
  const others = report.rules.filter(rule => rule.status !== "triggered");
  const evaluated = report.rules.some(rule => rule.status === "clear" || rule.status === "triggered");
  return <Panel title="Адресная диагностика" caption={`${report.aggregate_id} · ${report.pump_model || "Модель не задана"}`}>
    <p className="muted">{report.note}</p>
    {report.rules.length > 0 && <>
      {!triggered.length && <p className="notice diagnostic-notice">{evaluated
        ? "По выполненным правилам признаки не обнаружены. Невыполненные проверки не означают норму."
        : "Проверки не выполнены: сначала подтвердите привязку и необходимые основания. Это не заключение об исправности."}</p>}
      {(Object.keys(categories) as DiagnosticRule["category"][]).map(category => {
        const items = triggered.filter(rule => rule.category === category);
        return items.length > 0 && <section className="diagnostic-category" key={category}>
          <h3>{categories[category]}</h3>
          {items.map(rule => <Rule key={rule.id} rule={rule} />)}
        </section>;
      })}
      {others.length > 0 && <details className="diagnostic-remaining">
        <summary>Остальные проверки ({others.length}) — результаты и ограничения</summary>
        {(Object.keys(categories) as DiagnosticRule["category"][]).map(category => {
          const items = others.filter(rule => rule.category === category);
          return items.length > 0 && <section className="diagnostic-category" key={category}>
            <h3>{categories[category]}</h3>
            {items.map(rule => <Rule key={rule.id} rule={rule} />)}
          </section>;
        })}
      </details>}
    </>}
  </Panel>;
}
export { Rule as DiagnosticRuleCard };
