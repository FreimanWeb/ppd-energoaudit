import { Tooltip } from "../shared/ui/Tooltip";
import { useResource, segment } from "../shared/api";
import { Plot, type Trace } from "../charts/Plot";
import { Panel } from "../shared/ui/Panel";
import { Status } from "../shared/ui/Status";
import { Table } from "../shared/ui/Table";
import { contextBody, type PageProps } from "../shared/ui/context";
import { fmt } from "../shared/ui/format";
type Working = {
  qh: { q: number; h: number }[];
  qeta: { q: number; eta: number }[];
  system: { q: number; h: number }[];
  point: { q: number; h: number; eta: number };
  nominal: { q: number | null; h: number | null; eta: number | null };
  due: { h: number | null; eta: number | null };
  origin: { qh: string; qeta: string; system: string };
  notes: string[];
  pump_kind: string;
};
export function WorkingPointPage(p: PageProps) {
  const valid = Boolean(
    p.objectId &&
      p.aggregateId &&
      (p.source === "field_trip" || (p.day && p.timestamp)),
  );
  const resource = useResource<Working>(
    valid
      ? `/objects/${segment(p.objectId)}/aggregates/${segment(p.aggregateId)}/working-point`
      : null,
    contextBody(p),
  );
  const data = resource.data;
  const origin = (value: string) =>
    value === "passport" ? "паспортная" : "оценочная модель";
  const point = (
    name: string,
    q: number | null,
    h: number | null,
    color: string,
  ): Trace => ({
    type: "scatter",
    mode: "markers",
    name,
    x: q == null ? [] : [q],
    y: h == null ? [] : [h],
    marker: {
      size: 12,
      color,
      symbol: name === "Номинальная точка" ? "diamond" : "circle",
    },
  });
  return (
    <Panel
      title="Рабочая точка: насос × трубопровод"
      help="Фактическая точка и доступные характеристики оборудования. Источники характеристик указаны в легенде."
    >
      <Status {...resource} empty="Выберите режим и момент измерения." />
      {p.audit?.quality.status === "unfit" && (
        <p className="notice error">
          Исходный режим непригоден для достоверных выводов. Показанные точки
          требуют уточнения измерений.
        </p>
      )}
      {data && (
        <>
          {(data.origin.qh !== "passport" ||
            data.origin.qeta !== "passport" ||
            data.origin.system !== "passport") && (
            <p className="notice">
              {data.pump_kind === "объёмный"
                ? "Для объёмного насоса показаны фактические точки; оценочные центробежные кривые не применяются."
                : "Пунктиром показаны оценочные характеристики. Для проверки рабочей точки нужны паспортные кривые оборудования."}
              {data.notes.length > 0 && (
                <Tooltip label="Основание характеристик" content={data.notes.join(" ")} />
              )}
            </p>
          )}
          {data.origin.qh === "passport" &&
            data.origin.qeta === "passport" &&
            data.origin.system === "passport" &&
            data.notes.length > 0 && (
              <p className="muted">
                Источники характеристик
                <Tooltip label="Основание характеристик" content={data.notes.join(" ")} />
              </p>
            )}
          <div className="chart-grid">
            <Plot
              title="Характеристика Q–H"
              data={[
                ...(data.qh.length
                  ? [
                      {
                        type: "scatter",
                        mode: "lines",
                        name: `Насос (${origin(data.origin.qh)})`,
                        x: data.qh.map((x) => x.q),
                        y: data.qh.map((x) => x.h),
                        line: {
                          color: "var(--chart-primary)",
                          dash: data.origin.qh === "passport" ? "solid" : "dot",
                        },
                      } as Trace,
                    ]
                  : []),
                ...(data.system.length
                  ? [
                      {
                        type: "scatter",
                        mode: "lines",
                        name: "Трубопровод (оценка)",
                        x: data.system.map((x) => x.q),
                        y: data.system.map((x) => x.h),
                        line: { color: "var(--chart-secondary)", dash: "dot" },
                      } as Trace,
                    ]
                  : []),
                point(
                  "Фактическая точка",
                  data.point.q,
                  data.point.h,
                  "var(--chart-status-warning)",
                ),
                point(
                  "Номинальная точка",
                  data.nominal.q,
                  data.nominal.h,
                  "var(--chart-status-success)",
                ),
                point("Должный напор", data.point.q, data.due.h, "var(--chart-status-danger)"),
              ]}
              layout={{
                xaxis: { title: { text: "Q, м³/ч" } },
                yaxis: { title: { text: "H, м" } },
              }}
            />
            <Plot
              title="Характеристика Q–η"
              data={[
                ...(data.qeta.length
                  ? [
                      {
                        type: "scatter",
                        mode: "lines",
                        name: `КПД насоса (${origin(data.origin.qeta)})`,
                        x: data.qeta.map((x) => x.q),
                        y: data.qeta.map((x) => x.eta * 100),
                        line: {
                          color: "var(--chart-primary)",
                          dash:
                            data.origin.qeta === "passport" ? "solid" : "dot",
                        },
                      } as Trace,
                    ]
                  : []),
                point(
                  "КПД установки (факт)",
                  data.point.q,
                  data.point.eta * 100,
                  "var(--chart-status-warning)",
                ),
                point(
                  "Номинальная точка",
                  data.nominal.q,
                  data.nominal.eta == null ? null : data.nominal.eta * 100,
                  "var(--chart-status-success)",
                ),
                point(
                  "Должный КПД",
                  data.point.q,
                  data.due.eta == null ? null : data.due.eta * 100,
                  "var(--chart-status-danger)",
                ),
              ]}
              layout={{
                xaxis: { title: { text: "Q, м³/ч" } },
                yaxis: { title: { text: "КПД, %" } },
              }}
            />
          </div>
          <p className="muted">
            Рабочая подача {fmt(data.point.q)} м³/ч · фактический напор{" "}
            {fmt(data.point.h)} м · КПД установки {fmt(data.point.eta * 100)} %.
            <Tooltip label="КПД установки и насоса" content="КПД установки включает двигатель и трансмиссию; паспортная Q–η относится только к насосу." />
          </p>
          <details>
            <summary>Координаты характеристик</summary>
            <h3>Q–H</h3>
            <Table
              rows={data.qh}
              columns={[
                { key: "q", label: "Q, м³/ч" },
                { key: "h", label: "H, м" },
              ]}
            />
            <h3>Q–η</h3>
            <Table
              rows={data.qeta.map((x) => ({ ...x, eta: x.eta * 100 }))}
              columns={[
                { key: "q", label: "Q, м³/ч" },
                { key: "eta", label: "η, %" },
              ]}
            />
          </details>
        </>
      )}
    </Panel>
  );
}
