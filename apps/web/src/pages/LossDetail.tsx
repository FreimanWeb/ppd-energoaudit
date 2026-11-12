import { useEffect } from "react";
import { segment, useResource } from "../shared/api";
import { Panel } from "../shared/ui/Panel";
import { Status } from "../shared/ui/Status";
import { Table } from "../shared/ui/Table";
import { LinkButton } from "../shared/ui/Button";
import { contextBody, type PageProps } from "../shared/ui/context";
import { fmt } from "../shared/ui/format";
import { DiagnosticRuleCard } from "../features/overview/Diagnostics";
import type { DiagnosticRule } from "../shared/types";
import { Benchmarks, DefectHistory } from "../features/recommendations/Evidence";
import type { Defects, MotorBenchmark, PumpBenchmark } from "../features/recommendations/types";
import { measureHref } from "../features/losses/measureCatalog.mjs";
import { LossProposals } from "../features/losses/LossProposals";
import "../features/recommendations/recommendations.css";

type Column = { key: string; label: string; digits?: number };
type Detail = {
  key: string;
  title: string;
  stage: "hall" | "pipes" | "wells";
  power_kw: number | null;
  share: number | null;
  annual_kwh: number | null;
  annual_money_krub: number | null;
  t_year: number;
  tariff: number;
  formula: string;
  inputs: { label: string; value: number | string | null; unit: string; source: string }[];
  components: { title: string; columns: Column[]; rows: Record<string, unknown>[] };
  notes: string[];
  checks: DiagnosticRule[];
  defects: Defects | null;
  motor_benchmark: MotorBenchmark | null;
  pump_benchmark: PumpBenchmark | null;
  network_status: string | null;
  quality: { status: string; issues: string[] };
  annual_runtime_is_assumed: boolean;
};

const backLabels: Record<string, string> = { losses: "К карте потерь", "machine-losses": "К карте потерь машинного блока" };
const stagePages: Record<string, string> = { hall: "machine-block", pipes: "pipelines", wells: "wells" };

export function LossDetailPage(p: PageProps & { loss: string; from: string }) {
  useEffect(() => { window.scrollTo({ top: 0, behavior: "instant" }); }, [p.loss]);
  const ready = p.loss && p.objectId && p.aggregateId && (p.source === "field_trip" || p.timestamp);
  const resource = useResource<Detail>(
    ready ? `/objects/${segment(p.objectId)}/aggregates/${segment(p.aggregateId)}/loss-detail` : null,
    contextBody(p, { loss: p.loss }),
  );
  const data = resource.data;
  const back = <LinkButton href={`#${p.from}`}>{backLabels[p.from] ?? "Назад"}</LinkButton>;
  if (!p.loss) return <Panel title="Составляющая потерь" action={back}><p className="notice">Выберите столбец на карте потерь.</p></Panel>;
  return <Panel title={data?.title ?? "Составляющая потерь"} action={back}>
    <Status {...resource} empty="Выберите агрегат и режим." />
    {data && <>
      {data.quality.status === "unfit" && <p className="notice">Режим непригоден для экономических выводов: {data.quality.issues.join(" ")}</p>}
      <div className="page-kpis">
        <div>Мощность потерь, кВт<strong>{fmt(data.power_kw, 1)}</strong></div>
        <div>Доля потреблённой мощности, %<strong>{fmt(data.share === null ? null : data.share * 100, 1)}</strong></div>
        <div>Энергия, тыс. кВт·ч/год<strong>{fmt(data.annual_kwh === null ? null : data.annual_kwh / 1000, 0)}</strong></div>
        <div>Стоимость, тыс. ₽/год<strong>{fmt(data.annual_money_krub, 0)}</strong></div>
      </div>
      <p className="muted">Год: {fmt(data.t_year, 0)} ч{data.annual_runtime_is_assumed ? " (принято)" : ""} · тариф {fmt(data.tariff, 2)} ₽/кВт·ч.</p>
      <p className="formula-line">{data.formula}</p>
      {data.inputs.length > 0 && <section aria-label="Исходные величины"><h3>Исходные величины</h3>
        <Table rows={data.inputs} columns={[
          { key: "label", label: "Величина" }, { key: "value", label: "Значение", digits: 3 },
          { key: "unit", label: "Ед.", align: "start" }, { key: "source", label: "Основание", align: "start" },
        ]} />
      </section>}
      {data.components.rows.length > 0 && <section aria-label="Состав"><h3>{data.components.title}</h3>
        <Table rows={data.components.rows} columns={data.components.columns} />
      </section>}
      {data.components.columns.length > 0 && data.components.rows.length === 0 && data.network_status !== "scenario" &&
        <p className="notice">Расчёт сети для этого режима недоступен.</p>}
      {data.notes.map((note, index) => <p className="muted" key={index}>{note}</p>)}
      {data.checks.length > 0 && <section aria-label="Адресная диагностика"><h3>Адресная диагностика</h3>{data.checks.map(rule => <DiagnosticRuleCard key={rule.id} rule={rule} />)}</section>}
      {data.stage === "hall" && p.objectId && p.aggregateId && <LossProposals lossKey={data.key} context={{ objectId: p.objectId, aggregateId: p.aggregateId, source: p.source, timestamp: p.timestamp }} />}
      <Benchmarks pump={data.pump_benchmark} motor={data.motor_benchmark} />
      <DefectHistory defects={data.defects} />
      <div className="content-actions">
        <LinkButton href={measureHref(null, data.stage)}>Мероприятия участка</LinkButton>
        <LinkButton href={`#${stagePages[data.stage]}`}>Показатели участка</LinkButton>
        {data.stage === "hall" && <LinkButton href="#recommendations">Диагностика и рекомендации</LinkButton>}
      </div>
    </>}
  </Panel>;
}
