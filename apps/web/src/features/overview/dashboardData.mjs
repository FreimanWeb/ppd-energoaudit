/** @param {any} audit */
export function dashboardData(audit) {
  const usable = audit.quality.status !== "unfit";
  return {
    usable,
    dailySec: audit.scope.daily_kpi_is_fact
      ? (audit.audit.metrics.sec_fact_kwh_m3 ?? null)
      : null,
    regimeSec: audit.scope.daily_kpi_is_fact
      ? null
      : (audit.audit.metrics.sec_fact_kwh_m3 ?? null),
    source:
      audit.source === "field_trip" ? "Выездной замер (YAML)" : "Телеметрия",
    timestamp:
      audit.source === "field_trip"
        ? null
        : (audit.snapshot?.timestamp ?? null),
    regimeBasis:
      audit.source === "field_trip"
        ? audit.regime?.measured_at
          ? `Выездной замер: ${audit.regime.measured_at}; время внутри суток не задано.`
          : "Исходный режим из YAML; время измерения не задано."
        : audit.snapshot?.timestamp
          ? `Выбранный снимок: ${audit.snapshot.timestamp.replace("T", " ")}.`
          : "Время исходного режима не задано.",
    annual: usable ? (audit.annual_summary ?? null) : null,
    losses: usable ? (audit.losses ?? []) : [],
    runtime: audit.scope.annual_runtime_is_assumed
      ? "Сценарий непрерывной работы; фактическая годовая наработка требует уточнения."
      : audit.source === "field_trip"
        ? "Годовая наработка из YAML-паспорта."
        : "Годовая наработка по телеметрии.",
  };
}
