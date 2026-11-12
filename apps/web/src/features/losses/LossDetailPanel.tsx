import { useEffect, useRef, useState } from "react";
import { segment, useResource } from "../../shared/api";
import { contextBody, type PageProps } from "../../shared/ui/context";
import { fmt } from "../../shared/ui/format";
import { Table } from "../../shared/ui/Table";
import { LinkButton } from "../../shared/ui/Button";
import { inspectionFor, lossInspectionKey } from "../inspection/inspection.mjs";
import { readNetworkScenario } from "./networkScenario.mjs";
import { RequirementList } from "../manual/requirements";
import type { LossComponent, LossDetail } from "../../shared/types";
import { MathEquation } from "../../pages/MathEquation";

const originText: Record<LossComponent["origin"], string> = {
  measured: "Измерено",
  calculated: "Рассчитано",
  assumed: "Допущение",
  unavailable: "Нет данных",
};
const statusText: Record<LossDetail["status"], string> = {
  ready: "Составляющие распределены по расчётной модели. Это не подтверждённый потенциал экономии.",
  partial: "Разбор имеет ограничения: доступны только показанные расчётные значения. Неизвестные потери нулём не подменяются.",
  unavailable: "Разбор недоступен: исходных данных недостаточно для расчёта этого участка.",
};

// Участки и составляющие ниже БГ: серверный разбор опирается на баланс оператора
// (граница wellhead_after_choke), гидравлический сценарий сохраняется в запросе.
const downstreamKeys: Record<string, true> = { pipes: true, wells: true, friction_loss: true, local_loss: true, pipes_loss: true, choke_loss: true, bore_loss: true };
// Ключи разбора, поддержанные сервером: стадия, физические части машинного блока
// и причинные колонки с точными значениями.
export const physicalHallKeys: Record<string, true> = {
  vfd_loss: true, motor_chain_loss: true, transmission_loss: true, pump_loss: true, hydraulic_bg_loss: true,
};
export const causalHallKeys: Record<string, true> = {
  hall_causal: true, efficiency_causes: true,
  efficiency_loss: true, nominal_loss: true, throttle_loss: true, pump_bg_loss: true,
  wear_loss: true, suboptimal_loss: true, motor_loss: true, viscosity_loss: true,
};
const supportedKeys: Record<string, true> = {
  ...downstreamKeys, hall: true, ...physicalHallKeys, ...causalHallKeys,
};

/** Ключ серверного разбора для inspect: поддержанный ключ либо причинная колонка,
 *  на которую указывает метрика (eta_unit → efficiency_loss и т.п.). */
export function lossDetailKey(inspectionKey?: string): string | undefined {
  if (!inspectionKey) return undefined;
  if (supportedKeys[inspectionKey]) return inspectionKey;
  const loss = inspectionFor(inspectionKey)?.loss;
  const mapped = loss ? lossInspectionKey(loss) : undefined;
  return mapped && supportedKeys[mapped] ? mapped : undefined;
}

/** Разбор потерь участка или одной составляющей: физическая декомпозиция,
 *  формулы с подстановками, исходные значения и требования к данным. */
export function LossDetailPanel({ context, focus, stageHref }: { context: PageProps; focus: string; stageHref?: string }) {
  const [leaf, setLeaf] = useState<string | null>(null);
  const leafRef = useRef<HTMLDivElement>(null);
  useEffect(() => { leafRef.current?.scrollIntoView({block: "nearest"}); }, [leaf]);
  const rawScenario = downstreamKeys[focus] ? new URL(location.href).searchParams.get("network_scenario") : null;
  const scenario = rawScenario ? readNetworkScenario(rawScenario) : null;
  const invalidScenario = Boolean(rawScenario && !scenario);
  const resource = useResource<LossDetail>(
    !invalidScenario && context.objectId && context.aggregateId && (context.source === "field_trip" || context.timestamp)
      ? `/objects/${segment(context.objectId)}/aggregates/${segment(context.aggregateId)}/loss-detail` : null,
    contextBody(context, { key: focus, ...(scenario ? { scenario } : {}) }),
  );
  const data = resource.data;
  const isStage = focus === "hall" || focus === "hall_causal" || focus === "pipes" || focus === "wells";
  const select = (componentKey: string) => {
    const url = new URL(location.href);
    url.searchParams.set("inspect", componentKey);
    history.pushState(null, "", url.href);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };
  const allHref = (() => {
    const url = new URL(location.href);
    url.searchParams.delete("inspect");
    return `${url.pathname}${url.search}${url.hash}`;
  })();
  const many = isStage || (data?.components.length ?? 0) > 1;
  const selectedLeaf = leaf ? data?.components.find(item => item.key === leaf) : undefined;
  return <div className="loss-detail" aria-label="Разбор потерь">
    {invalidScenario && <p className="notice error" role="alert">Параметры сетевого сценария некорректны. Значениями по умолчанию они не заменены.</p>}
    {resource.error && <p className="notice error" role="alert">{resource.error}</p>}
    {resource.loading && <p className="notice" role="status">Рассчитываем разбор потерь…</p>}
    {!data && !resource.loading && !resource.error && <p className="notice">Выберите режим агрегата для разбора потерь.</p>}
    {data && <>
      <header className="loss-selection-heading"><h3>{data.title}</h3>
        {!isStage && <LinkButton href={stageHref ?? allHref}>Весь разбор участка</LinkButton>}
      </header>
      {data.boundary && <p className="muted">{data.boundary}</p>}
      <p className={`notice loss-detail-status ${data.status}`}>{statusText[data.status]}</p>
      <dl className="network-balance-totals" aria-label="Итог разбора">
        <div><dt>Входная мощность</dt><dd>{fmt(data.input_kw)} кВт</dd></div>
        <div><dt>Выходная мощность</dt><dd>{fmt(data.output_kw)} кВт</dd></div>
        <div><dt>{isStage ? "Потери участка" : "Значение составляющей"}</dt><dd>{fmt(data.total_kw)} кВт</dd></div>
        {!many && data.components[0] && <div><dt>Доля электрического ввода</dt><dd>{data.components[0].share_pct == null ? "Не определена" : `${fmt(data.components[0].share_pct, 1)} %`}</dd></div>}
        {data.unallocated_kw != null && data.unallocated_kw !== 0 && <div><dt>Нераспределённый остаток</dt><dd>{fmt(data.unallocated_kw)} кВт</dd></div>}
        {data.balance_residual_kw != null && Math.abs(data.balance_residual_kw) > 1e-6 && <div><dt>Невязка баланса</dt><dd>{fmt(data.balance_residual_kw, 3)} кВт</dd></div>}
      </dl>
      <details className="stage-assumptions"><summary>Годовой сценарий по этому режиму</summary>
        <p>Наработка {fmt(data.annual_runtime_hours)} ч{data.annual_runtime_is_assumed ? " — допущение" : ""} · тариф {fmt(data.tariff)} ₽/кВт·ч.</p>
        <p>{fmt(data.annual_kwh)} кВт·ч/год · {fmt(data.annual_rub)} ₽/год. Это экстраполяция режима, не измеренные годовые потери.</p>
      </details>
      {many && data.components.length > 0 && <Table
        rowHighlighted={row => row.key === leaf}
        rows={data.components.map(item => ({ ...item, origin_label: originText[item.origin] ?? item.origin }))}
        columns={[
          { key: "name", label: "Составляющая", render: row => supportedKeys[String(row.key)]
            ? <button type="button" className="link-button" onClick={() => select(String(row.key))}>{String(row.name)}</button>
            : <button type="button" className="link-button" onClick={() => setLeaf(String(row.key))}>{String(row.name)}</button> },
          { key: "power_kw", label: "Мощность, кВт", digits: 6 },
          { key: "share_pct", label: "Доля от P_эл, %", digits: 1 },
          { key: "origin_label", label: "Происхождение" },
        ]}
      />}
      {selectedLeaf && <div ref={leafRef}><ComponentDetail item={selectedLeaf} heading={selectedLeaf.name}/></div>}
      {!many && data.components.map(item => <ComponentDetail key={item.key} item={item}
        heading={item.name === data.title ? "Основание расчёта" : item.name} />)}
      {data.requirements.length > 0 && <section aria-label="Исходные данные и ограничения">
        <h3>Исходные данные и ограничения</h3>
        <RequirementList items={data.requirements} compact />
      </section>}
      {data.notes.length > 0 && <details className="stage-assumptions"><summary>Примечания к расчёту</summary>
        <ul>{data.notes.map((note, index) => <li key={index}>{note}</li>)}</ul>
      </details>}
    </>}
  </div>;
}

function ComponentDetail({ item, heading = "Основание расчёта" }: { item: LossComponent; heading?: string }) {
  return <article className="loss-component" data-component={item.key}>
    <header><h4>{heading}</h4><span className="loss-origin">{originText[item.origin] ?? item.origin}</span></header>
    {item.formula_latex && <MathEquation latex={item.formula_latex}/>}
    {item.substitution_latex ? <MathEquation latex={item.substitution_latex}/>
      : item.substitution && <p className="loss-substitution">{item.substitution}</p>}
    {item.basis && <p className="muted">{item.basis}</p>}
    {item.inputs.length > 0 && <Table rows={item.inputs.map(input => ({ ...input, origin: originText[input.origin as LossComponent["origin"]] ?? input.origin }))} columns={[
      { key: "label", label: "Вход" }, { key: "value", label: "Значение", digits: 6 }, { key: "unit", label: "Единица" },
      { key: "origin", label: "Происхождение" },
      { key: "source", label: "Источник" },
    ]} />}
  </article>;
}
