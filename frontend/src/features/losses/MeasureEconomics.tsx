import {useState} from "react";
import {Tooltip} from "../../shared/ui/Tooltip";
import {Status} from "../../shared/ui/Status";
import {Table} from "../../shared/ui/Table";
import {contextBody,type PageProps} from "../../shared/ui/context";
import {fmt} from "../../shared/ui/format";
import {segment,useResource} from "../../shared/api";
import {Plot,type Trace} from "../../charts/Plot";
import {economicDisplay} from "../../pages/fidelity.mjs";

export type Annual = {
  measure_id: string;
  name: string;
  cls: string;
  energy_saving_kwh: number;
  money_saving_krub: number;
  capex_krub: number;
  payback_years: number | null;
  note: string;
  addresses?: string;
};
type Year = {
  year: number;
  injection_m3: number;
  volume_ratio: number;
  energy_saving_kwh: number;
  money_saving_krub: number;
  discount_factor: number;
  discounted_krub: number;
  cumulative_krub: number;
  cumulative_discounted_krub: number;
};
type Horizon = {
  cls: string;
  measure_id: string;
  name: string;
  capex_krub: number;
  total_energy_kwh: number;
  total_money_krub: number;
  total_discounted_krub: number;
  npv_krub: number | null;
  irr: number | null;
  payback_years: number | null;
  discounted_payback_years: number | null;
  years: Year[];
  note: string;
};
type Profile = {
  base_annual_m3: number;
  annual_m3: number[];
  lower_annual_m3: number[] | null;
  upper_annual_m3: number[] | null;
  method: string;
  estimate: boolean;
  extrapolated_tail: boolean;
  note: string;
};
export type Measures = {
  annual: Annual[];
  profile: Profile | null;
  horizon: Horizon[];
  setpoint: {
    current_p_out: number;
    optimal_p_out: number;
    sec_current: number;
    sec_optimal: number;
    saving_kwh_year: number;
    vfd_freq_hz: number | null;
    within_constraints: boolean;
    notes: string[];
  };
  optimized_horizon: { energy_kwh: number; money_krub: number } | null;
  notes: string[];
  scope: { annual_runtime_hours: number; annual_runtime_is_assumed: boolean };
  tariff: number;
};
export function MeasureEconomics({context,measureId,baseline}:{context:PageProps;measureId:string;baseline:Measures}) {
  const [investment,setInvestment]=useState(false),[years,setYears]=useState(3),[rate,setRate]=useState(15),[period,setPeriod]=useState(30);
  const valid=Number.isInteger(years) && years>=1 && years<=10 && Number.isFinite(rate) && rate>=0 && rate<=60;
  const resource=useResource<Measures>(investment && valid ? `/objects/${segment(context.objectId)}/aggregates/${segment(context.aggregateId)}/measures` : null,
    contextBody(context,{basis:"forecast",horizon_years:years,discount_rate:rate/100,period_days:period}));
  const annual=baseline.annual.find(row=>row.measure_id===measureId);
  const annualDisplay=annual ? economicDisplay(annual) : undefined;
  const data=investment ? resource.data : baseline;
  const chosen=investment ? data?.horizon.find(row=>row.measure_id===measureId) : undefined;
  const profile=investment ? data?.profile : null;
  const cash=chosen?.years ?? [];
  const displayed=chosen ? economicDisplay(chosen) : undefined;
  const noPressureChange=Boolean(data && Math.abs(data.setpoint.current_p_out-data.setpoint.optimal_p_out)<1e-9 && Math.abs(data.setpoint.saving_kwh_year)<1e-6);
  const profileData: Trace[] = profile
    ? [
        {
          type: "scatter",
          mode: "lines+markers",
          name: "Прогноз",
          x: profile.annual_m3.map((_, i) => i + 1),
          y: profile.annual_m3,
          line: { color: "var(--chart-primary)" },
        },
      ]
    : [];
  if (profile?.lower_annual_m3 && profile.upper_annual_m3)
    profileData.unshift(
      {
        type: "scatter",
        mode: "lines",
        name: "Нижняя граница",
        x: profile.annual_m3.map((_, i) => i + 1),
        y: profile.lower_annual_m3,
        line: { width: 0 },
        showlegend: false,
      },
      {
        type: "scatter",
        mode: "lines",
        name: "Интервал прогноза",
        x: profile.annual_m3.map((_, i) => i + 1),
        y: profile.upper_annual_m3,
        line: { width: 0 },
        fill: "tonexty",
        fillcolor: "color-mix(in srgb, var(--chart-primary) 12%, transparent)",
      },
    );
  return <section aria-label="Экономика мероприятия">
    <div className="metric-segments" role="group" aria-label="Оценка мероприятия">
      <button type="button" aria-pressed={!investment} onClick={()=>setInvestment(false)}>Годовой эффект</button>
      <button type="button" aria-pressed={investment} onClick={()=>setInvestment(true)}>Инвестиционная оценка</button>
    </div>
    {investment && <div className="page-controls">
      <label>Горизонт, лет<input aria-label="Горизонт экономики" type="number" min={1} max={10} step={1} value={years} onChange={event=>setYears(Number(event.target.value))}/></label>
      <label>Ставка дисконтирования, %<input aria-label="Ставка дисконтирования" type="number" min={0} max={60} value={rate} onChange={event=>setRate(Number(event.target.value))}/></label>
      <label>Период профиля<select aria-label="Период профиля" value={period} onChange={event=>setPeriod(Number(event.target.value))}>
        <option value={1}>Сутки</option><option value={7}>Неделя</option><option value={30}>Месяц</option>
      </select></label>
    </div>}
    {investment && (!valid ? <p className="notice error" role="alert">Горизонт: целое число от 1 до 10 лет; ставка: от 0 до 60 %.</p> : <Status {...resource}/>)}
    {data && <>
      {data.notes.slice(1).map((note,index)=><p className="notice" key={index}>{note}</p>)}
      <p className="muted">Тариф {fmt(data.tariff)} ₽/кВт·ч · годовая наработка {fmt(data.scope.annual_runtime_hours,0)} ч{data.scope.annual_runtime_is_assumed ? " (допущение)" : ""}. Эффекты альтернативных мероприятий не суммируются.</p>
    </>}
    {!investment && annual && <>
      <dl className="network-balance-totals">
        <div><dt>Годовая сценарная экономия</dt><dd>{fmt(annual.energy_saving_kwh,0)} кВт·ч/год</dd></div>
        <div><dt>Денежный эффект</dt><dd>{fmt(annual.money_saving_krub)} тыс. ₽/год</dd></div>
        <div><dt>CAPEX, тыс. ₽</dt><dd>{fmt(annualDisplay?.capex_krub)}</dd></div>
        <div><dt>Окупаемость</dt><dd>{annual.cls==="сценарная оценка" ? "Требует оценки" : annual.capex_krub===0 ? "Без CAPEX" : annual.payback_years===null ? "Не определена" : `${fmt(annual.payback_years)} лет`}</dd></div>
      </dl>
      <p className="muted">Сценарий сохранения выбранного режима и принятой годовой наработки. Достижимость эффекта требует проверки.</p>
    </>}
    {investment && chosen && <>
      {chosen.cls==="сценарная оценка" && <p className="notice">CAPEX требует оценки; NPV и окупаемость не определены.</p>}
                  <div className="page-kpis">
                    <div>
                      NPV, тыс. ₽<Tooltip label="NPV" content="Будущая экономия с учётом ставки дисконтирования минус первоначальные вложения." /><strong>{fmt(displayed?.npv_krub)}</strong>
                    </div>
                    <div>
                      IRR, %<Tooltip label="IRR" content="Ставка, при которой NPV равен нулю. Прочерк означает, что показатель не определён." />
                      <strong>
                        {fmt(displayed?.irr)}
                      </strong>
                    </div>
                    <div>
                      Окупаемость, лет
                      <strong>
                        {chosen.cls === "сценарная оценка" ? "Требует оценки" : chosen.payback_years === null
                          ? "Не достигнута"
                          : fmt(chosen.payback_years)}
                      </strong>
                    </div>
                    <div>
                      С дисконтом, лет
                      <strong>
                        {chosen.cls === "сценарная оценка" ? "Требует оценки" : chosen.discounted_payback_years === null
                          ? "Не достигнута"
                          : fmt(chosen.discounted_payback_years)}
                      </strong>
                    </div>
                  </div>
                  <Plot
                    title="Накопленный денежный эффект"
                    data={[
                      {
                        type: "scatter",
                        mode: "lines+markers",
                        name: "Без дисконта",
                        x: [0, ...cash.map((c) => c.year)],
                        y: [0, ...cash.map((c) => c.cumulative_krub)],
                        line: { color: "var(--chart-primary)" },
                      },
                      {
                        type: "scatter",
                        mode: "lines+markers",
                        name: "С дисконтом",
                        x: [0, ...cash.map((c) => c.year)],
                        y: [
                          0,
                          ...cash.map((c) => c.cumulative_discounted_krub),
                        ],
                        line: { color: "var(--chart-status-warning)" },
                      },
                    ]}
                    layout={{
                      xaxis: { title: { text: "Год" }, dtick: 1 },
                      yaxis: { title: { text: "Накопленный эффект, тыс. ₽" } },
                      shapes: chosen.cls === "сценарная оценка" ? [] : [
                        {
                          type: "line",
                          xref: "paper",
                          x0: 0,
                          x1: 1,
                          yref: "y",
                          y0: chosen.capex_krub,
                          y1: chosen.capex_krub,
                          line: { color: "var(--chart-status-danger)", dash: "dot" },
                        },
                      ],
                    }}
                  />
                  <p className="muted">
                    <Tooltip label="Денежный поток" content={chosen.cls === "сценарная оценка" ? "Вложения требуют оценки, поэтому линия окупаемости не построена. Прочерк IRR означает, что показатель не определён." : `Пунктир — вложения (CAPEX ${fmt(chosen.capex_krub)} тыс. ₽). Прочерк IRR означает, что показатель не определён.`} />
                  </p>
                  <details className="metric-disclosure">
                    <summary>Годовой денежный поток</summary>
                  <Table
                    rows={cash}
                    columns={[
                      { key: "year", label: "Год" },
                      { key: "injection_m3", label: "Закачка, м³" },
                      { key: "volume_ratio", label: "К базовому году", help: "Отношение объёма закачки этого года к базовому объёму. Масштабирует сценарную экономию." },
                      { key: "energy_saving_kwh", label: "Энергия, кВт·ч" },
                      { key: "money_saving_krub", label: "Эффект, тыс. ₽" },
                      { key: "discount_factor", label: "Дисконт-фактор", help: "Коэффициент приведения будущего денежного эффекта к текущему году по выбранной ставке." },
                      { key: "discounted_krub", label: "С дисконтом, тыс. ₽" },
                      { key: "cumulative_krub", label: "Накоплено, тыс. ₽" },
                      {
                        key: "cumulative_discounted_krub",
                        label: "Накоплено с дисконтом",
                      },
                    ]}
                  />
                  </details>
                  <p className="notice">{chosen.note}</p>
    </>}
    {investment && data && !chosen && <p className="notice" role="status">Инвестиционная оценка выбранного мероприятия для этого режима недоступна.</p>}
          {profile?.estimate && (
            <p className="notice">
              Экономика использует оценочный профиль закачки.
              {profile.extrapolated_tail && " Горизонт продлён последним прогнозным периодом."}
            </p>
          )}
          {profile && (
            <details className="metric-disclosure">
              <summary>Прогнозный профиль закачки</summary>
              <p className="muted">
                Сценарный профиль
                {profile.extrapolated_tail ? " · Продлён последним прогнозным периодом" : ""}
                <Tooltip label="Основание профиля закачки" content={<>{profile.method} · {profile.note}</>} />
              </p>
              <div className="page-kpis">
                <div>
                  Базовый год, м³
                  <strong>{fmt(profile.base_annual_m3, 0)}</strong>
                </div>
                <div>
                  За горизонт, м³
                  <strong>
                    {fmt(
                      profile.annual_m3.reduce((s, v) => s + v, 0),
                      0,
                    )}
                  </strong>
                </div>
              </div>
              <Plot
                title="Годовой профиль закачки"
                data={profileData}
                layout={{
                  xaxis: { title: { text: "Год" }, dtick: 1 },
                  yaxis: { title: { text: "Закачка, м³/год" } },
                }}
              />
              <Table
                rows={profile.annual_m3.map((value, i) => ({
                  year: i + 1,
                  value,
                  lower: profile.lower_annual_m3?.[i],
                  upper: profile.upper_annual_m3?.[i],
                }))}
                columns={[
                  { key: "year", label: "Год" },
                  { key: "value", label: "Объём, м³" },
                  { key: "lower", label: "Нижняя граница" },
                  { key: "upper", label: "Верхняя граница" },
                ]}
              />
            </details>
          )}

    {data && ["throttle_down","vfd"].includes(measureId) && <details className="metric-disclosure"><summary>Расчёт уставки для выбранного режима</summary>
          <h3>Оптимизация уставок<Tooltip label="Оптимизация уставок" content="Расчёт целевого давления с учётом технологических ограничений. Экономия — сценарий, а не достигнутый эффект; изменение уставки требует инженерной проверки." /></h3>
          <p
            className={`notice ${data.setpoint.within_constraints ? "" : "error"}`}
          >
            {data.setpoint.within_constraints
              ? "Уставка в пределах технологических ограничений"
              : "Технологические ограничения нарушены"}
          </p>
          {noPressureChange && (
            <p className="notice">
              Расчёт не предлагает экономичного изменения выходного давления в выбранном режиме.
              Текущая уставка сохранена; расчётная годовая экономия — 0 кВт·ч.
            </p>
          )}
          <details className="metric-disclosure" open={noPressureChange ? undefined : true}>
            <summary>Расчётные параметры уставки</summary>
          <div className="page-kpis">
            <div>
              Выходное давление: текущее → целевое, МПа
              <strong>
                {fmt(data.setpoint.current_p_out)} →{" "}
                {fmt(data.setpoint.optimal_p_out)}
              </strong>
            </div>
            <div>
              УРЭ: текущее → целевое, кВт·ч/м³
              <strong>
                {fmt(data.setpoint.sec_current, 3)} →{" "}
                {fmt(data.setpoint.sec_optimal, 3)}
              </strong>
            </div>
            <div>
              Экономия, кВт·ч/год
              <strong>{fmt(data.setpoint.saving_kwh_year, 0)}</strong>
            </div>
            <div>
              Частота ПЧ, Гц<strong>{fmt(data.setpoint.vfd_freq_hz)}</strong>
            </div>
          </div>
          </details>
          <ul className="warnings">
            {data.setpoint.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
          {data.optimized_horizon && (
            <p className="muted">
              Эффект уставки за горизонт:{" "}
              {fmt(data.optimized_horizon.energy_kwh, 0)} кВт·ч ·{" "}
              {fmt(data.optimized_horizon.money_krub)} тыс. ₽.
            </p>
          )}
    </details>}
  </section>;
}
