import { segment, useResource } from "../shared/api";
import { Panel } from "../shared/ui/Panel";
import { Status } from "../shared/ui/Status";
import { contextBody, type PageProps } from "../shared/ui/context";
import { fmt } from "../shared/ui/format";
import { LinkButton } from "../shared/ui/Button";
import { Diagnostics } from "../features/overview/Diagnostics";
import { Benchmarks, DefectHistory } from "../features/recommendations/Evidence";
import type { Recommendations } from "../features/recommendations/types";
import "../features/recommendations/recommendations.css";

export function RecommendationsPage(p: PageProps) {
  const ready = p.objectId && p.aggregateId && (p.source === "field_trip" || p.timestamp);
  const resource = useResource<Recommendations>(
    ready ? `/objects/${segment(p.objectId)}/aggregates/${segment(p.aggregateId)}/recommendations` : null,
    contextBody(p),
  );
  const data = resource.data;
  const values = data?.values ?? {};
  const range = data?.pump_range;
  const drop = values.p_out_mpa != null && values.p_bg_mpa != null ? values.p_out_mpa - values.p_bg_mpa : null;
  const triggered = data?.diagnostics.rules.filter(rule => rule.status === "triggered").length ?? 0;
  const evaluated = data?.diagnostics.rules.filter(rule => rule.status === "triggered" || rule.status === "clear").length ?? 0;
  return <>
    <Panel title="Рекомендации по насосному агрегату" action={<LinkButton href="#reference">Справочник</LinkButton>}>
      <Status {...resource} empty="Выберите агрегат и режим." />
      {data && <>
        <p className="muted">{data.pump_model} · {data.motor_model}</p>
        {data.quality.status === "unfit" && <p className="notice">Режим непригоден для достоверных выводов: {data.quality.issues.join(" ")}</p>}
        <div className="page-kpis">
          <div>Признаков для проверки<strong>{triggered} из {evaluated} выполненных</strong></div>
          <div>Подача / Q_ном, м³/ч<strong>{fmt(values.q_m3h, 1)} / {fmt(values.q_nom_m3h, 0)}</strong></div>
          <div>КПД установки факт / ном.<strong>{fmt(values.eta_unit, 3)} / {fmt(values.eta_nom, 3)}</strong></div>
          <div>Перепад насос — БГ, МПа<strong>{fmt(drop, 2)}</strong></div>
        </div>
      </>}
    </Panel>
    {data && <Diagnostics report={data.diagnostics} />}
    {data && <Panel title="Справочные сведения по агрегату">
      {range && <section aria-label="Рабочая область насоса">
        <h3>Рабочая область</h3>
        {range.found
          ? <p>По приложению к алгоритму ({range.size}, напор {fmt(range.head_m, 0)} м): {fmt(range.q_min_m3h, 0)}–{fmt(range.q_max_m3h, 0)} м³/ч, подача {range.q_in_range ? "в пределах" : "вне пределов"}.</p>
          : <p>{range.note} Подача {range.q_in_range ? "в пределах" : "вне пределов"} {fmt(range.q_min_m3h, 0)}–{fmt(range.q_max_m3h, 0)} м³/ч.</p>}
      </section>}
      <Benchmarks pump={data.pump_benchmark} motor={data.motor_benchmark} />
      <DefectHistory defects={data.defects} />
      <p className="reference-sources">Источники: {data.sources.filter(Boolean).join("; ")}.</p>
    </Panel>}
  </>;
}
