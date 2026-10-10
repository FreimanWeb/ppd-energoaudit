/** @param {any} audit */
export function dashboardData(audit) {
  const usable = audit.quality.status !== "unfit";
  return {
    usable,
    source:
      audit.source === "field_trip" ? "Выездной замер (YAML)" : "Телеметрия",
    timestamp:
      audit.source === "field_trip"
        ? null
        : (audit.snapshot?.timestamp ?? null),
    annual: usable ? (audit.annual_summary ?? null) : null,
    losses: usable ? (audit.losses ?? []) : [],
    runtime: audit.scope.annual_runtime_is_assumed
      ? "Сценарий непрерывной работы; фактическая годовая наработка требует уточнения."
      : audit.source === "field_trip"
        ? "Годовая наработка из YAML-паспорта."
        : "Годовая наработка по телеметрии.",
  };
}
