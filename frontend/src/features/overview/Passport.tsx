import { formatEfficiency } from "../../shared/format/number.mjs";
import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { Dictionary } from "./Dictionary";
import { segment, useResource } from "../../shared/api";
import { Status } from "../../shared/ui/Status";

export function Passport({ audit }: { audit: Audit }) {
  const runtime = useResource<{ reading: { hours: number; as_of: string; basis: string; source: string } | null }>(
    `/objects/${segment(audit.audit.object_id)}/aggregates/${segment(audit.audit.aggregate_id)}/runtime-reading`,
  );
  const p = audit.passport?.pump,
    m = audit.passport?.motor,
    rm = audit.regime,
    view = dashboardData(audit);
  return (
    <details className="page-panel passport-panel">
      <summary>
        <svg className="passport-chevron" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="m6 9 6 6 6-6" />
        </svg>
        <h2>Паспорт и исходный режим</h2>
      </summary>
        <div className="chart-grid">
          <div>
            <h3>Насос</h3>
            <Dictionary values={{
              Модель: p?.model,
              Тип: p?.kind,
              "Номинальная подача (Q_ном), м³/ч": p?.q_nom,
              "Номинальный напор (H_ном), м": p?.h_nom,
              "Номинальный КПД насоса (η_нас.ном)": formatEfficiency(p?.eta_nom),
              "Номинальная мощность (P_ном), кВт": p?.power_nom,
              "Частота вращения (n), об/мин": p?.n_rpm,
              "Наработка с начала эксплуатации, ч": audit.passport?.runtime_total_h,
              "Кривая подачи и напора (Q–H)": p?.curve_qh?.length ? "Паспортные координаты" : "Отсутствует",
              "Кривая подачи и КПД (Q–η)": p?.curve_qeta?.length ? "Паспортные координаты" : "Отсутствует",
            }} />
          </div>
          <div>
            <h3>Электродвигатель и передача</h3>
            <Dictionary values={{
              Модель: m?.model,
              Тип: m?.synchronous ? "синхронный" : "асинхронный",
              "Номинальная мощность (P_ном), кВт": m?.p_nom,
              "Номинальный КПД ЭД (η_ЭД.ном)": formatEfficiency(m?.eta_nom),
              "Коэффициент мощности (cos φ)": m?.cos_phi,
              "Напряжение (U), кВ": m?.voltage_kv,
              "Частотный преобразователь": audit.passport?.vfd ? "Есть" : "Нет",
              "КПД трансмиссии": formatEfficiency(audit.passport?.transmission?.efficiency),
            }} />
          </div>
        </div>
        <div className="chart-grid">
          <div>
            <h3>{view.source === "Телеметрия" ? "Измерения режима" : "Выездной замер"}</h3>
            <Dictionary values={{
              Источник: view.source,
              ...(view.timestamp ? { "Время замера": view.timestamp.replace("T", " ") } : {}),
              "Давление на приёме (p_вх), МПа": rm.p_in,
              "Давление на выкиде (p_вых), МПа": rm.p_out,
              "Давление блока гребёнок (p_БГ), МПа": rm.p_bg,
              "Перепад давления (Δp), МПа": rm.p_out - rm.p_in,
            }} />
          </div>
          <div>
            <h3>Суточные данные и свойства жидкости</h3>
            <Dictionary values={{
              "Плотность (ρ), кг/м³": rm.rho,
              "Кинематическая вязкость (ν), сСт": rm.nu,
              "Объём закачки за сутки (Q_сут), м³": rm.q_day,
              "Наработка за сутки (T_сут), ч": rm.t,
              "Энергия за сутки (W), кВт·ч": rm.w,
              "Мгновенная подача (Q), м³/ч": rm.q_fact,
              "Средняя электрическая мощность (P_эл), кВт": rm.p_electric,
              "Годовая наработка (T_год), ч": rm.t_year,
            }} />
          </div>
        </div>
        <section aria-label="Накопленная наработка агрегата">
          <h3>Накопленная наработка</h3>
          <Status {...runtime} empty="Нет сведений о накопленной наработке." />
          {runtime.data?.reading ? <>
            <Dictionary values={{
              "Наработка с начала эксплуатации, ч": runtime.data.reading.hours,
              "Дата показания": runtime.data.reading.as_of,
            }} />
            <p className="muted">{runtime.data.reading.basis}</p>
            <p className="muted">Источник: {runtime.data.reading.source}</p>
            <p className="muted">Накопленный счётчик не используется вместо годовой наработки в расчётах энергии.</p>
          </> : runtime.data && <p className="muted">Показание накопленной наработки не предоставлено.</p>}
        </section>
    </details>
  );
}
