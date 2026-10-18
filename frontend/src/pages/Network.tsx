import { useResource, segment } from "../shared/api";
import { Plot, type Trace } from "../charts/Plot";
import { Panel } from "../shared/ui/Panel";
import { Status } from "../shared/ui/Status";
import { Table } from "../shared/ui/Table";
import type { PageProps } from "../shared/ui/context";
import { fmt } from "../shared/ui/format";

type Well = {
  well: string;
  q_m3h: number;
  path_length_m: number;
  p_after_choke_mpa: number | null;
  dp_friction_mpa: number | null;
  dp_other_mpa: number | null;
  dp_choke_mpa: number | null;
  friction_kw: number;
  other_kw: number;
  choke_kw: number;
  loss_kw: number;
  annual_kwh: number;
  flags: string[];
};
type Pipeline = {
  name: string;
  length_m: number;
  sizes: string;
  pipe_types: string;
  q_m3h: number;
  velocity_ms: number;
  dp_friction_mpa: number;
};
type NetworkView = {
  month: string | null;
  p_bg_mpa: number;
  p_bg_source: { kind: "telemetry" | "wells"; start: string | null; end: string | null };
  fluid: { rho: number };
  eta: number;
  eta_basis: "fact" | "nominal";
  tariff: number;
  totals: {
    q_m3h: number;
    friction_kw: number;
    other_kw: number;
    choke_kw: number;
    friction_kwh: number;
    other_kwh: number;
    choke_kwh: number;
    money_krub: number;
    excess_pressure_mpa: number | null;
  };
  wells: Well[];
  pipelines: Pipeline[];
  error?: string;
};

const TOP = 15;
const parts = [
  { key: "friction_kw", name: "Трение в водоводах", color: "var(--chart-primary)" },
  { key: "other_kw", name: "Задвижки и прочие", color: "var(--chart-status-neutral)" },
  { key: "choke_kw", name: "Штуцеры", color: "var(--chart-status-warning)" },
] as const;

function auditEta(p: PageProps): number | null {
  const audit = p.audit as
    | { audit: { metrics?: { eta_unit?: number | null } }; quality: { status: string } }
    | undefined;
  const eta = audit?.audit.metrics?.eta_unit;
  return audit && audit.quality.status !== "unfit" && eta && eta > 0 && eta <= 1 ? eta : null;
}

function sourceLine(view: NetworkView) {
  const s = view.p_bg_source;
  const pressure =
    s.kind === "telemetry" ? `p_БГ по телеметрии ${s.start} — ${s.end}` : "p_БГ по карточкам скважин";
  const eta = view.eta_basis === "fact" ? "КПД выбранного режима" : "номинальный КПД станции";
  return `Скважины: ${view.month ?? "—"} · ${pressure} · ρ ${fmt(view.fluid.rho, 0)} кг/м³ · ${eta} ${fmt(view.eta, 3)} · тариф ${fmt(view.tariff, 2)} ₽/кВт·ч`;
}

export function NetworkPage(p: PageProps) {
  const eta = auditEta(p);
  const resource = useResource<NetworkView>(
    p.objectId
      ? `/objects/${segment(p.objectId)}/network${eta ? `?eta=${eta.toFixed(4)}` : ""}`
      : null,
  );
  const view = resource.data?.error ? undefined : resource.data;
  const top = view
    ? [...view.wells]
        .sort((a, b) => b.loss_kw - a.loss_kw)
        .slice(0, TOP)
        .filter((w) => w.loss_kw > 0)
        .reverse()
    : [];
  const traces: Trace[] = parts.map((part) => ({
    type: "bar",
    orientation: "h",
    name: part.name,
    x: top.map((w) => w[part.key]),
    y: top.map((w) => w.well),
    marker: { color: part.color },
  }));
  const t = view?.totals;
  return (
    <Panel title="Водоводы и скважины">
      <Status {...resource} />
      {resource.data?.error && <p className="notice">{resource.data.error}</p>}
      {view && t && (
        <>
          <p className="muted">{sourceLine(view)}</p>
          <div className="page-kpis">
            <div>
              Давление на БГ, МПа<strong>{fmt(view.p_bg_mpa, 2)}</strong>
            </div>
            <div>
              Закачка, м³/ч<strong>{fmt(t.q_m3h, 1)}</strong>
            </div>
            <div>
              Потери в сети, кВт<strong>{fmt(t.friction_kw + t.other_kw + t.choke_kw, 1)}</strong>
            </div>
            <div>
              Годовые потери, тыс. ₽<strong>{fmt(t.money_krub, 0)}</strong>
            </div>
          </div>
          <div className="page-kpis">
            <div>
              Трение, тыс. кВт·ч/год<strong>{fmt(t.friction_kwh / 1000, 0)}</strong>
            </div>
            <div>
              Задвижки и прочие, тыс. кВт·ч/год<strong>{fmt(t.other_kwh / 1000, 0)}</strong>
            </div>
            <div>
              Штуцеры, тыс. кВт·ч/год<strong>{fmt(t.choke_kwh / 1000, 0)}</strong>
            </div>
            {t.excess_pressure_mpa ? (
              <div>
                Избыток давления на БГ, МПа<strong>{fmt(t.excess_pressure_mpa, 2)}</strong>
              </div>
            ) : null}
          </div>
          {top.length > 0 && (
            <Plot
              title="Потери мощности по скважинам, кВт"
              data={traces}
              layout={{
                barmode: "stack",
                height: Math.max(260, 26 * top.length + 90),
                margin: { l: 70, r: 20, t: 15, b: 60 },
                xaxis: { title: { text: "Мощность потерь, кВт" } },
              }}
            />
          )}
          <h3>Скважины</h3>
          <Table
            rows={view.wells.map((w) => ({
              ...w,
              path_length_m: w.path_length_m || null,
              annual_mwh: w.annual_kwh / 1000,
              note: w.flags.join("; "),
            }))}
            columns={[
              { key: "well", label: "Скважина", align: "start" },
              { key: "q_m3h", label: "Q, м³/ч", digits: 2 },
              { key: "path_length_m", label: "Путь, м", digits: 0 },
              { key: "p_after_choke_mpa", label: "p после шт., МПа", digits: 2 },
              { key: "dp_friction_mpa", label: "Трение, МПа", digits: 2 },
              { key: "dp_other_mpa", label: "Задвижки и прочие, МПа", digits: 2 },
              { key: "dp_choke_mpa", label: "Штуцер, МПа", digits: 2 },
              { key: "loss_kw", label: "Потери, кВт", digits: 1 },
              { key: "annual_mwh", label: "Потери, тыс. кВт·ч/год", digits: 0 },
              { key: "note", label: "Примечание", align: "start" },
            ]}
          />
          <h3>Водоводы с наибольшим трением</h3>
          <Table
            rows={view.pipelines.slice(0, TOP)}
            columns={[
              { key: "name", label: "Водовод", align: "start" },
              { key: "length_m", label: "Длина, м", digits: 0 },
              { key: "sizes", label: "D×s, мм", align: "start" },
              { key: "pipe_types", label: "Тип трубы", align: "start" },
              { key: "q_m3h", label: "Q, м³/ч", digits: 1 },
              { key: "velocity_ms", label: "Скорость, м/с", digits: 2 },
              { key: "dp_friction_mpa", label: "Трение, МПа", digits: 2 },
            ]}
          />
        </>
      )}
    </Panel>
  );
}
