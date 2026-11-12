import { efficiencyPercent } from "../../shared/format/number.mjs";
import { inspectionFor, sourceKeys } from "../inspection/inspection.mjs";
import { InspectionLinks } from "../inspection/InspectionLinks";
import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { Panel } from "../../shared/ui/Panel";
import { Table } from "../../shared/ui/Table";
import { Dictionary } from "./Dictionary";
import { Passport } from "./Passport";

const inputs: {
  key: keyof Audit["regime"];
  parameter: string;
  unit: string;
  source: string;
  basis?: string;
}[] = [
  { key: "p_in", parameter: "Давление на приёме · p_вх", unit: "МПа", source: "p_вх", basis: "pressure" },
  { key: "p_out", parameter: "Давление на выкиде · p_вых", unit: "МПа", source: "p_вых", basis: "pressure" },
  { key: "p_bg", parameter: "Давление на гребёнке · p_БГ", unit: "МПа", source: "p_БГ" },
  { key: "q_fact", parameter: "Измеренная подача · Q", unit: "м³/ч", source: "Q" },
  { key: "q_day", parameter: "Суточный объём · Q_сут", unit: "м³", source: "Q_сут" },
  { key: "t", parameter: "Суточная наработка · T_сут", unit: "ч", source: "T_сут" },
  { key: "w", parameter: "Суточная энергия · W_сут", unit: "кВт·ч", source: "W_сут" },
  { key: "p_electric", parameter: "Мощность для расчёта · P_эл", unit: "кВт", source: "P_эл", basis: "power" },
  { key: "power_daily_reported", parameter: "Мощность суточного отчёта · база неизвестна", unit: "кВт", source: "P_сут_отч" },
  { key: "rho", parameter: "Плотность · ρ", unit: "кг/м³", source: "ρ" },
  { key: "nu", parameter: "Вязкость · ν", unit: "сСт", source: "ν" },
  { key: "t_year", parameter: "Годовая наработка · T_год", unit: "ч", source: "T_год" },
];

export function SourcesView({ audit, inspectionKey }: { audit: Audit; inspectionKey?: string }) {
  const view = dashboardData(audit);
  const source = (key: string) =>
    audit.sources[key] ??
    (audit.source === "field_trip" ? audit.sources.YAML : undefined) ??
    "Не сохранён";
  const rows = inputs.map((input) => {
    const flowInput = audit.regime.q_fact == null ? "q_day" : "q_fact";
    const basis = input.key === flowInput
      ? audit.quality.basis.flow
      : input.basis ? audit.quality.basis[input.basis] : undefined;
    return {
      key: input.key,
      parameter: input.parameter,
      value: input.key === "t_year" ? audit.scope.annual_runtime_hours : audit.regime[input.key],
      unit: input.unit,
      source: input.key === "p_electric" && audit.quality.basis.power === "W_сут / T_сут"
        ? `W_сут: ${source("W_сут")}; T_сут: ${source("T_сут")}`
        : source(input.source),
      basis: input.key === "t_year" ? view.runtime : basis ?? "Не сохранено",
    };
  });
  const formulaIds = inspectionFor(inspectionKey)?.formulas ?? [];
  const passportRows = [
    ...(formulaIds.includes("14") ? [
      { parameter: "КПД двигателя номинальный", value: efficiencyPercent(audit.passport.motor.eta_nom), unit: "%" },
      { parameter: "КПД насоса номинальный", value: efficiencyPercent(audit.passport.pump.eta_nom), unit: "%" },
      { parameter: "КПД передачи", value: efficiencyPercent(audit.passport.transmission.efficiency), unit: "%" },
    ] : []),
    ...(formulaIds.includes("24") ? [
      { parameter: "Номинальная мощность ЭД", value: audit.passport.motor.p_nom, unit: "кВт" },
      { parameter: "КПД двигателя номинальный", value: efficiencyPercent(audit.passport.motor.eta_nom), unit: "%" },
    ] : []),
    ...(formulaIds.includes("27") ? [
      { parameter: "КПД передачи", value: efficiencyPercent(audit.passport.transmission.efficiency), unit: "%" },
      { parameter: "Наличие ПЧ", value: audit.passport.vfd ? "Есть" : "Нет", unit: "" },
    ] : []),
  ];
  const additionalSources = Object.fromEntries(
    Object.entries(audit.sources).filter(([key]) =>
      !inputs.some((input) => input.source === key),
    ),
  );
  const additionalBasis = Object.fromEntries(
    Object.entries(audit.quality.basis).filter(([key]) =>
      !["pressure", "flow", "power"].includes(key),
    ),
  );
  return (
    <><Panel title="Источники расчётных входов" caption={view.source}>
      {!Object.keys(audit.sources).length && (
        <p className="notice">Источники не сохранены у ранее загруженной телеметрии.</p>
      )}
      <InspectionLinks metric={inspectionKey} />
      {inspectionFor(inspectionKey)?.sources.length === 0 && <p className="muted">Основание — паспортные данные агрегата; полный паспорт приведён ниже.</p>}
      <Table
        rowHighlighted={row => sourceKeys(inspectionKey, audit).includes(String(row.key))}
        rows={rows}
        columns={[
          { key: "parameter", label: "Параметр" },
          { key: "value", label: "Значение", align: "end" },
          { key: "unit", label: "Единица" },
          { key: "source", label: "Источник" },
          { key: "basis", label: "Основание расчёта" },
        ]}
      />
      {passportRows.length > 0 && <section aria-label="Паспортные входы показателя">
        <h3>Паспортные входы показателя</h3>
        <Table rows={passportRows} columns={[{key: "parameter", label: "Параметр"}, {key: "value", label: "Значение", digits: 1}, {key: "unit", label: "Единица"}]} />
        <p className="muted">Паспорт выбранного агрегата. Источник файла для этих полей отдельно не сохранён в расчётном ответе.</p>
      </section>}
      <p className="muted">
        {audit.scope.daily_kpi_is_fact
          ? "Суточный УРЭ основан на W / Q_сут."
          : "Расход энергии относится к расчётному режиму."}
      </p>
      {audit.quality.issues.map((issue) => (
        <p className={issue.severity === "error" ? "notice error" : "notice"} key={issue.code}>
          {issue.message}
        </p>
      ))}
      {(Object.keys(additionalSources).length > 0 || Object.keys(additionalBasis).length > 0) && (
        <details>
          <summary>Дополнительные сведения об источниках</summary>
          {Object.keys(additionalSources).length > 0 && <Dictionary values={additionalSources} />}
          {Object.keys(additionalBasis).length > 0 && <Dictionary values={additionalBasis} />}
        </details>
      )}
    </Panel><Passport audit={audit}/></>
  );
}
