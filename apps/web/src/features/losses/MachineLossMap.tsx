import { useEffect, useRef } from "react";
import { segment, useResource } from "../../shared/api";
import type { LossDetail } from "../../shared/types";
import { contextBody, type PageProps } from "../../shared/ui/context";
import { Button, LinkButton } from "../../shared/ui/Button";
import { fmt } from "../../shared/ui/format";
import { Panel } from "../../shared/ui/Panel";
import { Status } from "../../shared/ui/Status";
import { inspectionFor, inspectionHref, hallReportHref } from "../inspection/inspection.mjs";
import { requirementHref } from "../manual/requirements";
import { lossDetailKey, physicalHallKeys } from "./LossDetailPanel";
import { MathEquation } from "../../pages/MathEquation";
import "./machineLossMap.css";

function selectLoss(key?: string) {
  const returnFocus = key ? null : document.querySelector<HTMLButtonElement>(".machine-loss-row[aria-pressed='true']")
    ?? document.querySelector<HTMLButtonElement>(".machine-loss-row");
  const url = new URL(location.href);
  if (key) url.searchParams.set("inspect", key);
  else url.searchParams.delete("inspect");
  url.searchParams.delete("decomposition");
  history.pushState(null, "", url.href);
  window.dispatchEvent(new PopStateEvent("popstate"));
  returnFocus?.focus();
}

function calculationProblem(data: LossDetail): string {
  const missing = data.requirements.filter(item => item.status === "missing");
  const reasons = [...new Set(data.requirements
    .filter(item => item.status === "missing" || item.status === "conflict")
    .map(item => item.reason).filter(Boolean))];
  return [missing.length ? `Не хватает данных: ${missing.map(item => item.label).join(", ")}.` : "", ...reasons].filter(Boolean).join(" ");
}

export function MachineLossMap({ context, inspectionKey, unfit, issues }: {
  context: PageProps; inspectionKey?: string; unfit: boolean; issues: string[];
}) {
  const resource = useResource<LossDetail>(
    !unfit && context.objectId && context.aggregateId && (context.source === "field_trip" || context.timestamp)
      ? `/objects/${segment(context.objectId)}/aggregates/${segment(context.aggregateId)}/loss-detail` : null,
    contextBody(context, {key: "hall"}),
  );
  const data = resource.data;
  const mapped = lossDetailKey(inspectionKey);
  const foreign = inspectionFor(inspectionKey)?.stage;
  const focus = mapped && mapped !== "hall" && (!foreign || foreign === "hall") ? mapped : undefined;
  const unknownSelection = Boolean(inspectionKey && inspectionKey !== "hall" && !focus);
  let low = 0, high = 0;
  for (const item of data?.components ?? []) {
    if (item.power_kw != null) { low = Math.min(low, item.power_kw); high = Math.max(high, item.power_kw); }
  }
  const span = high - low || 1;
  const conflicts = [...new Set(data?.requirements.filter(item => item.status === "conflict").map(item => item.reason) ?? [])];
  return <Panel title="Потери машинного блока" caption="Выберите составляющую, чтобы открыть её разбор.">
    <div className="machine-loss-map">
      {unfit ? <p className="notice error" role="alert">Карта недоступна для этого режима. {[...new Set(issues)].join(" ")}
        {" "}<LinkButton href={inspectionHref("onboarding", inspectionKey)}>Проверить данные</LinkButton>
      </p> : <Status {...resource} empty="Выберите пригодный режим агрегата."/>}
      {!unfit && data && <>
        <div className="machine-loss-total"><span>Общие потери до БГ</span>
          <strong>{fmt(data.total_kw)} <small>кВт</small></strong>
          <span className="muted">Расчёт по выбранному режиму</span>
          <dl className="machine-loss-balance" aria-label="Баланс мощности">
            <div><dt>Электрический ввод</dt><dd>{fmt(data.input_kw)} кВт</dd></div>
            <div><dt>Гидравлическая мощность на БГ</dt><dd>{fmt(data.output_kw)} кВт</dd></div>
            <div><dt>Доля потерь от ввода</dt><dd>{data.total_kw != null && data.input_kw != null && data.input_kw > 0 ? `${fmt(data.total_kw / data.input_kw * 100, 1)} %` : "Нет расчёта"}</dd></div>
          </dl>
          <LinkButton href={hallReportHref()}>Подробный расчёт</LinkButton>
        </div>
        {data.status === "unavailable" ? <p className="notice error" role="alert">
          {calculationProblem(data) || "Исходных данных недостаточно для расчёта потерь."}
          {" "}<LinkButton href={inspectionHref("onboarding", inspectionKey)}>Проверить данные</LinkButton>
        </p> : conflicts.length > 0 && <p className="notice error" role="alert">{conflicts.join(" ")}</p>}
        {data.unallocated_kw != null && data.unallocated_kw !== 0 && <p className="machine-loss-remainder">
          Не распределено по оборудованию: {fmt(data.unallocated_kw)} кВт. Часть характеристик неизвестна или противоречива.
        </p>}
        <ul className="machine-loss-bars" aria-label="Потери по оборудованию">
          {data.components.map(item => <li key={item.key}>
            <button type="button" className="machine-loss-row" aria-pressed={focus === item.key}
              onClick={() => selectLoss(item.key)}>
              <span className="machine-loss-name">{item.name}</span>
              <span className="machine-loss-track" data-unavailable={item.power_kw == null || undefined} aria-hidden="true">
                <span className="machine-loss-zero" style={{left: `${-low / span * 100}%`}}/>
                {item.power_kw != null && <span className={`machine-loss-fill${item.power_kw < 0 ? " negative" : ""}`}
                  style={{left: `${(Math.min(0, item.power_kw) - low) / span * 100}%`, width: `${Math.abs(item.power_kw) / span * 100}%`}}/>}
              </span>
              <span className="machine-loss-value">{item.power_kw == null ? "Нет расчёта" : `${fmt(item.power_kw)} кВт`}</span>
            </button>
          </li>)}
        </ul>
        {unknownSelection && <p className="notice">Выбранный показатель не является составляющей этой карты.
          {" "}<Button variant="secondary" onClick={() => selectLoss()}>Снять выбор</Button>
        </p>}
        {focus && <SelectedLoss key={focus} context={context} focus={focus} inputKw={data.input_kw}/>}
      </>}
    </div>
  </Panel>;
}

function SelectedLoss({context, focus, inputKw}: {context: PageProps; focus: string; inputKw: number | null}) {
  const resource = useResource<LossDetail>(
    `/objects/${segment(context.objectId)}/aggregates/${segment(context.aggregateId)}/loss-detail`,
    contextBody(context, {key: focus}),
  );
  const data = resource.data;
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!data) return;
    root.current?.scrollIntoView({block: "nearest"});
    root.current?.focus({preventScroll: true});
  }, [data]);
  const component = data?.components.length === 1 ? data.components[0] : undefined;
  const blockers = data?.requirements.filter(item => item.status === "missing" || item.status === "conflict") ?? [];
  const problem = data ? calculationProblem(data) : "";
  const correctionHref = blockers.length === 1 && blockers[0].action !== "review"
    ? requirementHref(blockers[0]) : inspectionHref("onboarding", focus);
  return <section ref={root} tabIndex={-1} className="machine-loss-selection" aria-label="Выбранная составляющая">
    <header><h3>{data?.title ?? inspectionFor(focus)?.title ?? "Разбор составляющей"}</h3>
      <Button variant="secondary" onClick={() => selectLoss()}>Закрыть разбор</Button>
    </header>
    <Status {...resource}/>
    {data && <>
      {!physicalHallKeys[focus] && <p className="muted">Составляющая другого разложения; столбцы выше показывают потери по оборудованию.</p>}
      <p className="machine-loss-selected-value">{data.total_kw == null ? "Нет расчёта" : `${component?.origin === "assumed" ? "≈ " : ""}${fmt(data.total_kw)} кВт`}</p>
      <p className="muted">{data.total_kw != null && inputKw != null && inputKw > 0
        ? `${fmt(data.total_kw / inputKw * 100, 1)} % электрического ввода агрегата`
        : "Доля электрического ввода не определена"}</p>
      {data.total_kw != null && <p>{component?.basis || data.boundary}</p>}
      {component?.formula_latex && <MathEquation latex={component.formula_latex}/>}
      {(problem || data.status === "unavailable") && <p className="notice error" role="alert">
        {problem || "Недостаточно данных для этой составляющей."}
        {" "}<LinkButton href={correctionHref}>Уточнить исходные данные</LinkButton>
      </p>}
      <nav className="machine-loss-links" aria-label="Действия для составляющей">
        <LinkButton href={hallReportHref(focus, physicalHallKeys[focus] ? "equipment" : "causal")}>Расчёт и источники</LinkButton>
        <LinkButton href={inspectionHref("measures", focus)}>Мероприятия</LinkButton>
      </nav>
    </>}
  </section>;
}
