import { useResource, segment } from "../api";
import { Panel, Status, Table, type PageProps } from "./common";
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
  return (
    <Panel
      title="Подключение объекта"
      caption="Требования к исходным данным, готовность выбранного агрегата и шаблоны для подготовки паспорта. Изменение данных выполняется через принятый процесс верификации."
    >
      <Status {...resource} />
      {data && (
        <>
          <h3>Телеметрия для энергоаудита</h3>
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
          <h3>Паспортные данные и замеры</h3>
          <ul className="requirements">
            {data.manual_requirements.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
          <h3>Готовность выбранного агрегата</h3>
          <Table
            rows={data.checks.map((check) => ({
              ...check,
              present: check.present ? "Есть" : "Не задано",
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
          {data.notes.map((n, i) => (
            <p className="notice" key={i}>
              {n}
            </p>
          ))}
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
