import { efficiencyPercent } from "../../shared/format/number.mjs";
import { metricLinks, metricKeys } from "../inspection/inspection.mjs";
import type { ReactNode } from "react";
import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { metricAssessment } from "../../shared/metrics/metricAssessment.mjs";
import { MetricCard } from "../../shared/ui/MetricCard";

export const metricHelp: Record<string, string> = {
  "УРЭ факт": "Суточный удельный расход электроэнергии: W / Q_сут за одни и те же сутки.\n\nБез обоих суточных итогов показатель отсутствует. Расчёт по режиму не подставляется вместо факта.",
  "УРЭ по режиму": "Отношение электрической мощности к подаче из исходного режима.\n\nЭто расчёт по доступным входным данным, а не измеренная суточная энергия на объём закачки.",
  "УРЭ расчётный": "По напору исходного режима и номинальному КПД.\n\nСуточный УРЭ и расчёт по отдельному замеру давления имеют разную временную базу; их разница сама по себе не доказывает потери.",
  "УРЭ оптимальный": "По оптимальному давлению; для КНС p_опт = p_БГ.\n\nБез подтверждённого оптимального режима показатель отсутствует.",
  "Цель ППД-2035": "Целевой удельный расход энергии системы ППД к 2035 году из конфигурации ТЗ.",
  "КПД агрегата": "Фактический КПД установки: гидравлическая мощность / электрическая мощность.\n\nСравнение с номинальным КПД.",
  "КПД номинальный": "Паспортный КПД установки: произведение КПД двигателя, насоса и передачи.",
  "Коэффициент загрузки ЭД": "Отношение расчётной мощности на валу к номинальной мощности электродвигателя.\n\nK > 1 означает перегрузку.",
  "КПД ЭД расчётный": "КПД электродвигателя с учётом загрузки.\n\nСравнивается с паспортным КПД ЭД.",
  "КПД насоса расчётный": "КПД насоса из фактического КПД установки с учётом двигателя и передачи.\n\nСравнивается с паспортным КПД насоса.",
  "Фактический напор": "Напор по перепаду p_вых − p_вх и плотности жидкости.\n\nСравнивается только с доступным должным напором.",
  "Подача": "Объёмный расход: мгновенный Q, если доступен, иначе Q_сут / T_сут.\n\nНоминальный расход сам по себе не задаёт границу исправности.",
  "Гидравлическая мощность": "Полезная мощность потока по расходу и перепаду давления.",
  "Электрическая мощность": "Мощность, используемая в расчёте: W_сут / T_сут либо значение выбранного снимка.",
  "Давление на приёме": "Давление жидкости перед насосом в выбранный момент измерения.",
  "Давление на выкиде": "Давление жидкости после насоса в выбранный момент измерения.",
  "Давление БГ": "Давление на блоке гребёнок; используется для оценки необходимого давления КНС и дросселирования.",
  "Должный напор": "Необходимый напор по методике и доступным данным; отсутствие значения не подменяется паспортным напором.",
  "Потери по КПД": "Годовая энергия потерь из-за снижения КПД.\n\nСценарная оценка по T_год, не достигнутая экономия.",
  "Потери по КПД в деньгах": "Годовые потери энергии по КПД, умноженные на тариф.\n\nСценарий, не фактическая экономия.",
  "Потери дросселирования": "Годовая энергия потерь из-за избыточного давления.\n\nСценарий по T_год, требует подтверждения оптимального режима.",
  "Потери дросселирования в деньгах": "Годовые потери дросселирования по тарифу.\n\nСценарная оценка, не достигнутая экономия.",
};
metricHelp["Напор факт"] = metricHelp["Фактический напор"];
metricHelp["КПД на выбранный момент"] = metricHelp["КПД агрегата"];

export function Kpis({
  rows,
  label,
  audit,
  heading = true,
  children,
}: {
  rows: [string, unknown, string][];
  label: string;
  audit: Audit;
  heading?: boolean;
  children?: ReactNode;
}) {
  const m = audit.audit.metrics, view = dashboardData(audit), usable = view.usable;
  const comparisons: Record<string, [unknown, "higher" | "lower", string, boolean?]> = {
    "УРЭ по режиму": [m.sec_calc_kwh_m3, "higher", "при паспортном КПД"],
    "КПД агрегата": [m.eta_nom, "lower", "номинального", true],
    "КПД на выбранный момент": [m.eta_nom, "lower", "номинального", true],
    "КПД ЭД расчётный": [audit.passport?.motor?.eta_nom, "lower", "паспортного", true],
    "КПД насоса расчётный": [audit.passport?.pump?.eta_nom, "lower", "паспортного", true],
    "Коэффициент загрузки ЭД": [1, "higher", "номинальной загрузки"],
    "Фактический напор": [m.h_due_m, "lower", "должного"],
    "Напор факт": [m.h_due_m, "lower", "должного"],
  };
  return (
    <section className="metric-group" aria-label={label}>
      {heading && <h3>{label}</h3>}
      <div className="kpis">
        {rows.map(([name, inputValue, unit]) => {
          const value = name === "УРЭ факт" ? view.dailySec : name === "УРЭ по режиму" ? view.regimeSec : inputValue;
          const comparison = comparisons[name];
          const annual = name.startsWith("Потери");
          const efficiency = comparison?.[3] ?? name === "КПД номинальный";
          const assessment = metricAssessment(value, annual ? 0 : comparison?.[0],
            annual ? "higher" : comparison?.[1] ?? "higher", usable,
            efficiency);
          let caption = assessment.caption;
          if (comparison && assessment.caption !== "Физическая ошибка" && (assessment.tone === "good" || assessment.tone === "bad")) {
            caption = value === comparison[0] ? `На уровне ${comparison[2]}` :
              Number(value) > Number(comparison[0]) ? `Выше ${comparison[2]}` : `Ниже ${comparison[2]}`;
          }
          if (name === "Коэффициент загрузки ЭД" && assessment.tone === "good") caption = "Без перегрузки";
          if (annual && assessment.tone !== "neutral")
            caption = Number(value) > 0 ? "Потери · сценарий" : "Нет потерь · сценарий";
          const displayName = name === "Коэффициент загрузки ЭД" ? "Коэф. загрузки ЭД" : name;
          const helpOnValue = ["Коэффициент загрузки ЭД", "КПД ЭД расчётный", "КПД насоса расчётный"].includes(name);
          return <MetricCard links={metricLinks(metricKeys[name])} key={name} label={displayName} value={efficiency ? efficiencyPercent(value) : value} unit={efficiency ? "%" : unit}
            help={metricHelp[name]} helpOnValue={helpOnValue} {...assessment} caption={caption} />;
        })}
        {children}
      </div>
    </section>
  );
}
