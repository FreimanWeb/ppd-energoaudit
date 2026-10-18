import { Button, LinkButton } from "../shared/ui/Button";
import { Tooltip } from "../shared/ui/Tooltip";
import { useState } from "react";
import { economicDisplay } from "./fidelity.mjs";
import { useResource, segment } from "../shared/api";
import { Plot, type Trace } from "../charts/Plot";
import { Panel } from "../shared/ui/Panel";
import { Status } from "../shared/ui/Status";
import { inspectionFor, relatedMeasures, inspectionHref } from "../features/inspection/inspection.mjs";
import { InspectionLinks } from "../features/inspection/InspectionLinks";
import { Table } from "../shared/ui/Table";
import { contextBody, type PageProps } from "../shared/ui/context";
import { ChainMeasures } from "../features/losses/ChainMeasures";
import { fmt } from "../shared/ui/format";
type Annual = {
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
type Measures = {
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
export function MeasuresPage(p: PageProps) {
  const [basis, setBasis] = useState("annual"),
    [years, setYears] = useState(3),
    [rate, setRate] = useState(15),
    [period, setPeriod] = useState(30),
    [measure, setMeasure] = useState("");
  const eligible = Boolean(
      p.objectId &&
        p.aggregateId &&
        (p.source === "field_trip" || (p.day && p.timestamp)) &&
        p.audit?.quality.status !== "unfit",
    ),
    valid = years >= 1 && years <= 10 && rate >= 0 && rate <= 60;
  const resource = useResource<Measures>(
    eligible && valid
      ? `/objects/${segment(p.objectId)}/aggregates/${segment(p.aggregateId)}/measures`
      : null,
    contextBody(p, {
      horizon_years: years,
      discount_rate: rate / 100,
      period_days: period,
      basis,
    }),
  );
  const data = resource.data;
  const related = relatedMeasures(data?.annual ?? [], p.inspectionKey);
  const focus = inspectionFor(p.inspectionKey);
  const horizonRows = focus ? data?.horizon.filter(item => related.some(annual => annual.measure_id === item.measure_id)) ?? [] : data?.horizon ?? [];
  const chosen =
      horizonRows.find((x) => x.measure_id === measure) ?? horizonRows[0],
    profile = data?.profile;
  const cash = chosen?.years ?? [];
  const displayed = chosen ? economicDisplay(chosen) : undefined;
  const noPressureChange = Boolean(data &&
    Math.abs(data.setpoint.current_p_out - data.setpoint.optimal_p_out) < 1e-9 &&
    Math.abs(data.setpoint.saving_kwh_year) < 1e-6);
  const annualColumns = [
    { key: "name", label: "Мероприятие" },
    { key: "cls", label: "Класс" },
    { key: "energy_saving_kwh", label: "Экономия, кВт·ч/год" },
    { key: "money_saving_krub", label: "Эффект, тыс. ₽/год" },
    { key: "capex_krub", label: "CAPEX, тыс. ₽", help: "Капитальные вложения. Типовые затраты требуют уточнения перед принятием решения." },
    { key: "payback_years", label: "Окупаемость, лет", help: "Время, за которое накопленная экономия покрывает вложения, без дисконтирования." },
    { key: "note", label: "Условия" },
  ];
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
  return (<>
    <ChainMeasures key={`${p.objectId}:${p.aggregateId}:${p.source}:${p.day}:${p.timestamp}`} context={p} annual={focus ? related : data?.annual ?? []} eligible={eligible} loading={resource.loading} error={resource.error} />
    <details className="metric-disclosure" open={focus ? true : undefined}><summary>Расширенный расчёт экономики машинного блока</summary>
    <Panel
      title="Мероприятия и экономика"
      caption="Расчёт агрегата и обвязки до БГ · CAPEX требует уточнения · экономия не подтверждена"
      help="Типовые затраты и расчётный эффект требуют диагностики. Это не проектное ТЭО и не достигнутая экономия."
    >
      <div className="page-controls">
        <label>
          Основание расчёта
          <select
            aria-label="Основание расчёта"
            value={basis}
            onChange={(e) => setBasis(e.target.value)}
          >
            <option value="annual">Текущий режим — годовой эффект</option>
            <option value="forecast">Прогноз закачки — горизонт</option>
          </select>
        </label>
        {basis === "forecast" && (
          <>
            <label>
              Горизонт, лет
              <input
                aria-label="Горизонт экономики"
                type="number"
                min={1}
                max={10}
                value={years}
                onChange={(e) => setYears(Number(e.target.value))}
              />
            </label>
            <label>
              Ставка дисконтирования, %
              <input
                aria-label="Ставка дисконтирования"
                type="number"
                min={0}
                max={60}
                value={rate}
                onChange={(e) => setRate(Number(e.target.value))}
              />
            </label>
            <label>
              Период профиля
              <select
                aria-label="Период профиля"
                value={period}
                onChange={(e) => setPeriod(Number(e.target.value))}
              >
                <option value={1}>Сутки</option>
                <option value={7}>Неделя</option>
                <option value={30}>Месяц</option>
              </select>
            </label>
          </>
        )}
      </div>
      {p.audit?.quality.status === "unfit" ? (
        <p className="notice error">
          Выбранный режим непригоден для экономических выводов. Уточните
          исходные измерения.
        </p>
      ) : !valid ? (
        <p className="notice error">
          Горизонт: от 1 до 10 лет; ставка: от 0 до 60 %.
        </p>
      ) : (
        <Status
          {...resource}
          empty="Выберите пригодный режим для расчёта мероприятий."
        />
      )}
      {data && (
        <>
          {data.notes.slice(1).map((n, i) => (
            <p className="notice" key={i}>{n}</p>
          ))}
          <p className="muted">
            Тариф {fmt(data.tariff)} ₽/кВт·ч · годовая наработка{" "}
            {fmt(data.scope.annual_runtime_hours, 0)} ч
            {data.scope.annual_runtime_is_assumed ? " (допущение)" : ""}.
            <Tooltip label="Расчёт годового эффекта" content="Эффекты разных мероприятий нельзя автоматически складывать: они могут устранять одни и те же потери." />
          </p>
          {focus && <section className="inspection-result" aria-label="Связанные мероприятия">
            <InspectionLinks metric={p.inspectionKey} />
            <h3>Мероприятия по выбранной причине потерь</h3>
            {related.length ? <Table rows={related.map(economicDisplay)} columns={annualColumns} />
              : <p className="notice">Для выбранной составляющей нет применимых мероприятий в реестре. Проверьте данные и технологические ограничения.</p>}
            <div className="content-actions"><LinkButton href={inspectionHref("losses", p.inspectionKey)}>Вернуться к составляющей потерь</LinkButton>
            <Button variant="secondary" onClick={() => { const url = new URL(location.href); url.searchParams.delete("inspect"); history.pushState(null, "", url); window.dispatchEvent(new PopStateEvent("popstate")); }}>Показать все мероприятия</Button></div>
          </section>}
          {!focus && <>
          <h3>Годовой реестр мероприятий</h3>
          <Table
            rows={data.annual.map(economicDisplay)}
            columns={annualColumns}
          />
          {data.annual.length > 0 && (
            <details className="metric-disclosure">
              <summary>Сравнить годовую экономию</summary>
            <Plot
              title="Годовой эффект мероприятий"
              data={[
                {
                  type: "bar",
                  orientation: "h",
                  x: data.annual.map((m) => m.energy_saving_kwh / 1000),
                  y: data.annual.map((m) => m.name),
                  marker: { color: "var(--chart-primary)" },
                },
              ]}
              layout={{
                margin: { l: 250, r: 25, t: 20, b: 50 },
                xaxis: { title: { text: "Экономия, тыс. кВт·ч/год" } },
                yaxis: { autorange: "reversed" },
              }}
            />
            </details>
          )}
          </>}
          {basis === "forecast" && (
            <>
              <h3>Экономика на горизонте</h3>
              {chosen && (
                <>
                  <label className="compact-control">
                    Мероприятие
                    <select
                      aria-label="Мероприятие денежного потока"
                      value={chosen.measure_id}
                      onChange={(e) => setMeasure(e.target.value)}
                    >
                      {horizonRows.map((m) => (
                        <option key={m.measure_id} value={m.measure_id}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {chosen.cls === "сценарная оценка" && (
                    <p className="notice">CAPEX требует оценки; NPV и окупаемость не определены.</p>
                  )}
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
                </>
              )}
              <details className="metric-disclosure">
                <summary>Сравнить экономику всех мероприятий</summary>
              <Table
                rows={data.horizon.map(economicDisplay)}
                columns={[
                  { key: "name", label: "Мероприятие" },
                  { key: "cls", label: "Класс" },
                  { key: "capex_krub", label: "CAPEX, тыс. ₽", help: "Капитальные вложения. Типовые затраты требуют уточнения перед принятием решения." },
                  { key: "total_energy_kwh", label: "Энергия, кВт·ч" },
                  { key: "total_money_krub", label: "Эффект, тыс. ₽" },
                  { key: "npv_krub", label: "NPV, тыс. ₽", help: "Чистый приведённый эффект: будущая экономия с учётом ставки дисконтирования минус первоначальные вложения." },
                  { key: "irr", label: "IRR, %", help: "Внутренняя доходность: ставка, при которой NPV равен нулю. Прочерк означает, что показатель не определён." },
                  { key: "payback_years", label: "Окупаемость, лет", help: "Время, за которое накопленная экономия покрывает вложения, без дисконтирования." },
                  {
                    key: "discounted_payback_years",
                    label: "С дисконтом, лет",
                  },
                ]}
              />
              </details>
            </>
          )}
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
        </>
      )}
    </Panel></details>
  </>);
}
