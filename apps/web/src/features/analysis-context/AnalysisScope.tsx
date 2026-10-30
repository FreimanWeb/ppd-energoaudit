import "./analysisScope.css";

export function AnalysisScope({page,aggregate,source,timestamp,well}: {
  page:string;aggregate:string;source:"telemetry"|"field_trip";timestamp:string;well:string;
}) {
  let scope = aggregate || "Агрегат не выбран";
  let basis = source === "field_trip" ? "Выездной замер" : "Выбранный режим";
  let note = "";
  let showTime = source === "telemetry";
  if (page === "overview") {
    scope = "Вся станция";
    basis = source === "field_trip" ? "Выездные данные всех учтённых НА" : "Последний общий режим учтённых НА";
    showTime = false;
  } else if (page === "timeline") {
    scope = aggregate || "Вся станция";
    basis = "История показателей";
    note = "Период истории задаётся на графиках. Дата и момент в панели — режим для детализации.";
    showTime = false;
  } else if (page === "well-history") {
    scope = well ? `Архив скважины ${well}` : "Архив скважин";
    basis = "Месячные записи и отдельные исследования";
    note = "Независимо от режима НА; даты относятся к архиву скважины.";
    showTime = false;
  } else if (page === "crm-wells") {
    scope = well ? `Скважина ${well}` : "Все скважины отчёта";
    basis = "Внешняя CRM-модель";
    note = "Сценарий и период отчёта выбираются ниже; режим НА не используется.";
    showTime = false;
  } else if (page === "network") {
    scope = well ? `Сеть · скважина ${well}` : "Разводящая сеть объекта";
    basis = "Реестр водоводов и карточки скважин";
    note = "Даты источников указаны в сводке сети; выбранный режим НА не используется.";
    showTime = false;
  } else if (page === "forecast" || page === "crm") {
    basis = "Прогноз по истории объёмов НА";
    note = "Период истории и горизонт прогноза задаются ниже.";
    showTime = false;
  } else if (["losses","network-scenario","pipelines","wells"].includes(page)) {
    scope = `Сценарий одного НА · ${scope}`;
    note = "Расход выбранного НА распределён по сети; совместная работа остальных НА в этом сценарии не учитывается.";
  }
  return <section className="analysis-scope" aria-label="Контекст анализа">
    <div><strong>{scope}</strong><span>{basis}</span>
      {showTime && (timestamp ? <time dateTime={timestamp}>{new Date(timestamp).toLocaleString("ru-RU")}</time> : <span>Момент режима не выбран</span>)}
    </div>
    {note && <p>{note}</p>}
  </section>;
}
