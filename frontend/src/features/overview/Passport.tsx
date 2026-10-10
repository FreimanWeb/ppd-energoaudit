import type { Audit } from "../../shared/types";
import { dashboardData } from "./dashboardData.mjs";
import { Dictionary } from "./Dictionary";
import { Panel } from "../../shared/ui/Panel";

export function Passport({ audit }: { audit: Audit }) {
  const p = audit.passport?.pump,
    m = audit.passport?.motor,
    rm = audit.regime,
    view = dashboardData(audit);
  return (
    <Panel title="Паспорт и исходный режим">
      <details className="metric-disclosure">
        <summary>Показать паспорт и исходные данные</summary>
        <div className="chart-grid">
          <div>
            <h3>Насос</h3>
            <Dictionary values={{
              Модель: p?.model,
              Тип: p?.kind,
              "Q_ном, м³/ч": p?.q_nom,
              "H_ном, м": p?.h_nom,
              "η_нас.ном, о.е.": p?.eta_nom,
              "P_ном, кВт": p?.power_nom,
              "n, об/мин": p?.n_rpm,
              "Кривая Q-H": p?.curve_qh?.length ? "Паспортные координаты" : "Отсутствует",
              "Кривая Q-η": p?.curve_qeta?.length ? "Паспортные координаты" : "Отсутствует",
            }} />
          </div>
          <div>
            <h3>Электродвигатель и передача</h3>
            <Dictionary values={{
              Модель: m?.model,
              Тип: m?.synchronous ? "синхронный" : "асинхронный",
              "P_ном, кВт": m?.p_nom,
              "η_ЭД.ном, о.е.": m?.eta_nom,
              "cos φ": m?.cos_phi,
              "U, кВ": m?.voltage_kv,
              ПЧ: audit.passport?.vfd ? "Есть" : "Нет",
              "КПД трансмиссии": audit.passport?.transmission?.efficiency,
            }} />
          </div>
        </div>
        <div className="chart-grid">
          <div>
            <h3>{view.source === "Телеметрия" ? "Показатель давления" : "Выездной замер"}</h3>
            <Dictionary values={{
              Источник: view.source,
              ...(view.timestamp ? { "Время замера": view.timestamp.replace("T", " ") } : {}),
              "p_вх, МПа": rm.p_in,
              "p_вых, МПа": rm.p_out,
              "p_БГ, МПа": rm.p_bg,
              "Δp, МПа": rm.p_out - rm.p_in,
            }} />
          </div>
          <div>
            <h3>Суточные данные и свойства жидкости</h3>
            <Dictionary values={{
              "ρ, кг/м³": rm.rho,
              "ν, сСт": rm.nu,
              "Q_сут, м³": rm.q_day,
              "Моточасы, ч": rm.t,
              "W, кВт·ч": rm.w,
              "Q мгновенный, м³/ч": rm.q_fact,
              "P_эл средняя, кВт": rm.p_electric,
              "T_год, ч": rm.t_year,
            }} />
          </div>
        </div>
      </details>
    </Panel>
  );
}
