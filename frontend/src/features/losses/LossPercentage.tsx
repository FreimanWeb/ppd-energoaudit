import { Plot } from "../../charts/Plot";
import { fmt } from "../../shared/ui/format";
import type { Loss } from "./LossCharts";

export function LossPercentage({ power, losses, onSelect }: { power: number; losses: Loss[]; onSelect?: (name: string) => void }) {
  if (!Number.isFinite(power) || power <= 0 || losses.some(item => !Number.isFinite(item.share)))
    return <p className="notice">Процентная структура недоступна: нет достоверной подведённой мощности или долей составляющих.</p>;
  if (losses.some(item => item.share < 0 || item.power_kw < 0))
    return <p className="notice">Для режима с отрицательными коррекциями выберите «Разложение». Исходные значения сохранены в таблице.</p>;
  const total = losses.reduce((sum, item) => sum + item.share, 0);
  if (total > 1 + 1e-6)
    return <p className="notice error">Сумма составляющих превышает 100%. Проверьте баланс мощности; все значения доступны в разложении и таблице.</p>;
  const colors = ["var(--chart-status-danger)", "var(--chart-status-warning)", "var(--chart-secondary)", "var(--chart-status-attention)"];
  const data = losses.filter(item => item.share > 0).map((item, index) => ({
    type: "bar", orientation: "h", name: item.name,
    x: [item.share * 100], y: [""],
    tooltip: [{ value: item.power_kw, unit: "кВт", share: item.share, selection: item.name }],
    customdata: [item.name],
    marker: { color: item.category === "полезная" ? "var(--chart-primary)" : colors[index % colors.length] },
  }));
  return <>
    <Plot onSelect={onSelect} title="Структура мощности, %" data={data} layout={{
      barmode: "relative", height: 210,
      xaxis: { range: [0, 100], title: { text: "Доля от подведённой мощности, %" } },
      yaxis: { visible: false }, margin: { l: 20, r: 20, t: 15, b: 65 },
    }} />
    <p className="muted">Показанные составляющие: {fmt(total * 100, 1)}% подведённой мощности.</p>
  </>;
}
