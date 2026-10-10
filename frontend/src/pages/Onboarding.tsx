import { Tooltip } from "../shared/ui/Tooltip";
import { useResource, segment } from "../shared/api";
import { Panel } from "../shared/ui/Panel";
import { Status } from "../shared/ui/Status";
import { Table } from "../shared/ui/Table";
import type { PageProps } from "../shared/ui/context";
type Onboarding = {
  telemetry_requirements: {
    parameter: string;
    symbol: string;
    unit: string;
    requirement: string;
    source: string;
  }[];
  manual_requirements: string[];
  checks: {
    field: string;
    present: boolean;
    value: number | unknown[] | null;
  }[];
  yaml_template: string;
  verification_template: string;
  notes: string[];
};
export function OnboardingPage(p: PageProps) {
  const resource = useResource<Onboarding>(
    p.objectId && p.aggregateId
      ? `/objects/${segment(p.objectId)}/aggregates/${segment(p.aggregateId)}/onboarding${p.source === "telemetry" && p.day ? `?at=${p.day}` : ""}`
      : null,
  );
  const data = resource.data;
  const basicFields = ["Телеметрия: p_вх", "Телеметрия: p_вых", "Плотность ρ",
    "Паспорт насоса: η_ном", "Паспорт ЭД: P_ном", "Паспорт ЭД: η_ном"];
  const missingBasic = data?.checks.filter(check => check.value == null && basicFields.includes(check.field)) ?? [];
  return (
    <Panel
      title="Готовность данных"
      help="Требования к исходным данным, готовность агрегата и шаблоны паспорта. Изменение данных выполняется через принятый процесс верификации."
    >
      <Status {...resource} />
      {data && (
        <>
          {missingBasic.length > 0 && <section className="notice error" aria-label="Недостающие базовые данные">
            <strong>Сначала заполните базовые данные для расчёта</strong>
            <ul>{missingBasic.map(check => <li key={check.field}>{check.field}</li>)}</ul>
          </section>}
          <h3>Готовность выбранного агрегата</h3>
          <Table
            rows={[...data.checks].sort((a, b) => Number(a.value != null) - Number(b.value != null)).map((check) => ({
              ...check,
              present: check.value != null ? "Есть" : "Не задано",
              value: Array.isArray(check.value)
                ? JSON.stringify(check.value)
                : check.value,
            }))}
            columns={[
              { key: "field", label: "Поле" },
              { key: "present", label: "Наличие" },
              { key: "value", label: "Значение" },
            ]}
          />

          {data.notes.map((note, index) => (
            <p className="notice" key={index}>{note}</p>
          ))}
          <details>
            <summary>Требования к телеметрии</summary>
            <Table
              rows={data.telemetry_requirements}
              columns={[
                { key: "parameter", label: "Параметр" },
                { key: "symbol", label: "Обозначение" },
                { key: "unit", label: "Единица" },
                { key: "requirement", label: "Требование" },
                { key: "source", label: "Источник" },
              ]}
            />
          </details>
          <details>
            <summary>Паспортные данные и замеры</summary>
            <ul className="requirements">
              {data.manual_requirements.map((r, i) => (
                <li key={i}>{r.includes("config/") ? <>{r.split(";")[0]}.<Tooltip label="Источник свойств жидкости" content={r} /></> : r}</li>
              ))}
            </ul>
          </details>
          <details>
            <summary>Шаблон паспорта объекта</summary>
            <pre className="template-code">{data.yaml_template}</pre>
          </details>
          <details>
            <summary>Шаблон записи для верификации</summary>
            <pre className="template-code">{data.verification_template}</pre>
          </details>
        </>
      )}
    </Panel>
  );
}
