import { useState } from "react";
import { Button } from "../shared/ui/Button";
import { MetricCard } from "../shared/ui/MetricCard";
import { Panel } from "../shared/ui/Panel";
import { Status } from "../shared/ui/Status";
import { Table } from "../shared/ui/Table";
import { Tooltip } from "../shared/ui/Tooltip";
import { Calendar } from "../features/analysis-context/Calendar";
import { calendarStatuses, measures, metricFixtures, pumpName } from "./fixtures";

const typography = ["caption", "label", "body", "body-large", "section", "page", "value"] as const;

export function DesignSystemPage() {
  const [day, setDay] = useState("2026-08-03");
  const [mode, setMode] = useState("analysis");
  const [action, setAction] = useState("Выберите действие для проверки состояния.");
  return <>
    <a className="skip-link" href="#catalogue-content">К компонентам</a>
    <main id="catalogue-content" className="catalogue">
      <div className="page-heading">
        <span className="eyebrow">ППД · локальный каталог</span>
        <h1>Дизайн-система</h1>
        <p>Рабочие компоненты приложения на демонстрационных данных. Таблица и календарь не используют реальную телеметрию.</p>
      </div>
      <nav aria-label="Разделы каталога" className="catalogue-nav">
        <a href="#typography">Типографика</a><a href="#metrics">Показатели</a>
        <a href="#controls">Управление</a><a href="#tables">Таблицы</a><a href="#states">Состояния</a>
      </nav>
      <div id="typography"><Panel title="Типографика">
        <div className="catalogue-type-list">{typography.map(role => <div key={role} className="catalogue-type-row">
          <code>--text-{role}</code><span className={`catalogue-type-${role}`}>Расход воды · 1 234,56 м³/ч</span>
        </div>)}</div>
      </Panel></div>
      <div id="metrics"><Panel title="Показатели" help="Проверьте ноль, отсутствие данных, крупные значения и превышение эталона. Цвет дополняется текстом в подсказке.">
        <h3 className="catalogue-pump-name">{pumpName}</h3>
        <div className="metric-group"><div className="kpis catalogue-metrics">
          {metricFixtures.map(metric => <MetricCard key={metric.label} {...metric} />)}
        </div></div>
        <div className="metric-group"><div className="kpis catalogue-pair">
          <MetricCard label="Потери по КПД" value={null} unit="" help="Энергетическая и денежная оценка одного вида потерь." segments={[
            { label: "Энергия", value: 156320.5, unit: "кВт·ч/год", help: "Годовая оценка энергии при текущем режиме." },
            { label: "Стоимость потерь", value: 1024769.28, unit: "₽/год", help: "Стоимость потерянной энергии по тарифу; это не затраты на внедрение мероприятия." },
          ]} />
        </div></div>
      </Panel></div>
      <div id="controls"><Panel title="Управление" caption="Tab проверяет focus. Escape закрывает подсказку и календарь.">
        <div className="catalogue-controls">
          <Button variant="primary" onClick={() => setAction("Расчёт запрошен. Это демонстрация, запрос к API не отправлялся.")}>Рассчитать</Button>
          <Button variant="secondary" onClick={() => setAction("Параметры восстановлены.")}>Сбросить параметры</Button>
          <Button variant="danger" onClick={() => setAction("Удаление не выполняется в каталоге.")}>Удалить</Button>
          <Button disabled>Недоступно</Button><Button loading>Загружаем</Button>
          <Tooltip label="Справка" content="Подсказка доступна по наведению, focus и нажатию. Закрывается по Escape." />
        </div>
        <p className="muted" role="status">{action}</p>
        <div className="page-controls">
          <label>Режим анализа<select value={mode} onChange={event => setMode(event.target.value)}>
            <option value="analysis">Суточный анализ</option><option value="snapshot">Режимный снимок</option>
          </select></label>
          <label>Агрегат без телеметрии<select disabled><option>Нет доступных агрегатов</option></select></label>
          <Calendar path="/design-system" day={day} dates={Object.keys(calendarStatuses)} onChange={setDay} />
        </div>
        <p className="muted">Выбрана дата: <time dateTime={day}>{day.split("-").reverse().join(".")}</time></p>
      </Panel></div>
      <div id="tables"><Panel title="Таблицы">
        <Table rows={measures} columns={[
          { key: "name", label: "Мероприятие" },
          { key: "cost", label: "Затраты, ₽", digits: 0, help: "Разовые затраты на проведение мероприятия." },
          { key: "saving", label: "Экономия, ₽/год", digits: 0, help: "Расчётное сокращение ежегодных затрат; не стоимость проведения." },
        ]} />
        <h3>Пустая таблица</h3><Table rows={[]} columns={[{ key: "name", label: "Мероприятие" }]} />
      </Panel></div>
      <div id="states"><Panel title="Состояния данных">
        <Status loading /><Status error="Не удалось загрузить телеметрию. Повторите запрос или проверьте источники." />
        <Status empty="На выбранную дату нет измерений. Выберите другую дату в календаре." />
      </Panel></div>
    </main>
  </>;
}
