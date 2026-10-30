import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { Tooltip } from "../../shared/ui/Tooltip";
import { formatEfficiency } from "../../shared/format/number.mjs";
import { fmt } from "../../shared/ui/format";

export function Quality({ audit, clarifications = [] }: { audit: Audit; clarifications?: {field: string; provisional_value: number | string; reason: string}[] }) {
  const view = dashboardData(audit);
  const clarificationLabels: Record<string, string> = {
    pump_eta_nom: "КПД насоса",
    motor_eta_nom: "КПД ЭД",
    t_year: "Годовая наработка",
    transmission_eff: "КПД трансмиссии",
  };
  return (
    <>
      {audit.quality.status !== "ready" && <div className={`quality ${audit.quality.status}`}>
        <strong>
          {audit.quality.status === "assumptions"
              ? "Расчёт с допущениями"
              : "Данные непригодны для достоверных выводов"}
        </strong>
        <span>
          {view.source} ·{" "}
          {audit.scope.daily_kpi_is_fact
            ? "Суточные измерения"
            : "По выбранному режиму · нет суточных итогов"}
          <Tooltip label="Основание расчёта" content={audit.scope.daily_kpi_is_fact
            ? <p>Фактический УРЭ рассчитан по суточной энергии и объёму закачки: W / Q_сут.</p>
            : <><p>Нет подтверждённых суточных энергии и объёма закачки. Показатели относятся к выбранному режиму.</p><p>Проверьте источники или выберите другие сутки.</p></>} />
        </span>
      </div>}
      {(audit.quality.issues.length > 0 || clarifications.length > 0) && (
        <ul className="warnings">
          {audit.quality.issues.map((issue, i) => (
            <li key={`${issue.code}-${i}`}>{issue.message}</li>
          ))}
          {clarifications.map((item, i) => (
            <li key={`clarification-${item.field}-${i}`}>
              <strong>Требует уточнения: {clarificationLabels[item.field] ?? item.field}</strong>{" — "}
              {["pump_eta_nom", "motor_eta_nom", "transmission_eff"].includes(item.field)
                ? formatEfficiency(item.provisional_value)
                : fmt(item.provisional_value)}. {item.reason}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
