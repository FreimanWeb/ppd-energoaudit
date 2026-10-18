import { LinkButton } from "../../shared/ui/Button";
import { segment, useResource } from "../../shared/api";
import type { PageProps } from "../../shared/ui/context";
import { contextBody } from "../../shared/ui/context";
import { Panel } from "../../shared/ui/Panel";
import { Status } from "../../shared/ui/Status";
import { Table } from "../../shared/ui/Table";

export function TopMeasures({ context }: { context: PageProps }) {
  const result = useResource<{ annual: Record<string, unknown>[] }>(
    `/objects/${segment(context.objectId)}/aggregates/${segment(context.aggregateId)}/measures`,
    contextBody(context, { basis: "annual" }),
  );
  return (
    <Panel title="Топ мероприятий" action={<LinkButton href="#measures">Все →</LinkButton>} help="Эвристическая оценка. Сценарные мероприятия требуют диагностики и оценки CAPEX. Отсутствие применимого мероприятия не означает, что потери в норме.">
      <Status {...result} empty="Мероприятия ещё не рассчитаны. Проверьте выбранный объект, агрегат и период." />
      {result.error && <LinkButton href="#sources">Проверить исходные данные</LinkButton>}
      {result.data && result.data.annual.length === 0 && <p className="notice">Для выбранного режима нет применимых мероприятий. Проверьте исходные данные или выберите другой период.</p>}
      {result.data && result.data.annual.length > 0 && (
        <Table
          rows={result.data.annual.slice(0, 3).map((r) => ({
            ...r,
            capex: r.cls === "сценарная оценка" ? "Требует оценки" : r.capex_krub,
            payback: r.cls === "сценарная оценка" ? "требует оценки" : (r.payback_years ?? "без CAPEX"),
          }))}
          columns={[
            { key: "name", label: "Мероприятие" },
            { key: "energy_saving_kwh", label: "кВт·ч/год", digits: 0 },
            { key: "money_saving_krub", label: "Эффект, тыс. ₽/год", help: "Годовой денежный эффект — снижение расходов на электроэнергию, а не затраты на внедрение." },
            { key: "capex", label: "Затраты CAPEX, тыс. ₽", help: "Разовые капитальные затраты на внедрение мероприятия. Для сценарной оценки требуется определить CAPEX; это не годовая экономия." },
            { key: "payback", label: "Окупаемость, лет" },
          ]}
        />
      )}
    </Panel>
  );
}
