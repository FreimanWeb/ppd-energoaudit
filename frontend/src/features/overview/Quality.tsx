import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { Tooltip } from "../../shared/ui/Tooltip";

export function Quality({ audit }: { audit: Audit }) {
  const view = dashboardData(audit);
  return (
    <>
      <div className={`quality ${audit.quality.status}`}>
        <strong>
          {audit.quality.status === "ready"
            ? "Данные пригодны для расчёта"
            : audit.quality.status === "assumptions"
              ? "Расчёт с допущениями"
              : "Данные непригодны для достоверных выводов"}
        </strong>
        <span>
          {view.source} ·{" "}
          {audit.scope.daily_kpi_is_fact
            ? "Суточные измерения"
            : "По выбранному режиму · нет суточных итогов"}
          <Tooltip label="Основание расчёта" content={audit.scope.daily_kpi_is_fact
            ? "Фактический УРЭ рассчитан по суточной энергии и объёму закачки: W / Q_сут."
            : "Нет подтверждённых суточных энергии и объёма закачки. Показатели относятся к выбранному режиму. Проверьте источники или выберите другие сутки."} />
        </span>
      </div>
      {audit.quality.issues.length > 0 && (
        <ul className="warnings">
          {audit.quality.issues.map((issue, i) => (
            <li key={`${issue.code}-${i}`}>{issue.message}</li>
          ))}
        </ul>
      )}
    </>
  );
}
