import { useEffect, useMemo, useRef, useState } from "react";
import { invalidateResources, segment, useResource } from "../shared/api";
import type { PageProps } from "../shared/ui/context";
import { Panel } from "../shared/ui/Panel";
import { Status } from "../shared/ui/Status";
import { Table } from "../shared/ui/Table";
import { Button } from "../shared/ui/Button";
import type { EquipmentData, EquipmentJournalResponse, EquipmentParameter, EquipmentResponse, JournalEntry, ManualMeasurement, PumpCurveSource } from "../shared/types";
import { journalPatch, normalizeEquipmentTime, parameterDifferences, parseEquipmentNumber, sameParameterValue } from "../features/manual/journalDraft.mjs";
import "../features/manual/manual.css";

type Props = PageProps & {
  onSelectMeasurement: (id: number | null, navigate?: boolean) => void;
  onEquipmentOverride: (data: EquipmentData | null) => void;
};
type Component = JournalEntry["component"];
type CurveKey = "pump.curve_qh" | "pump.curve_qeta";
type CurveRow = [string, string];
type MetaDraft = { effective_at: string; reason: JournalEntry["reason"]; evidence: JournalEntry["evidence"]; source: string; author: string; comment: string };
type SourceDraft = { kind: PumpCurveSource["kind"]; reference: string; model: string; speed_rpm: string; frequency_hz: string; verified: boolean; note: string };
type Payload = MetaDraft & { component: Component; expected_revision: string; changes: Record<string, unknown>; supersedes_id: number | null };
type SummaryRow = { key: string; parameter: string; before: string; after: string };
type Confirmation = { payload: Payload; rows: SummaryRow[]; replacement: boolean };

const COMPONENTS: {id: Component; label: string}[] = [
  {id: "pump", label: "Насос"}, {id: "motor", label: "Электродвигатель"},
  {id: "transmission", label: "Передача"}, {id: "vfd", label: "Частотное регулирование"},
];
const COMPONENT_LABEL = Object.fromEntries(COMPONENTS.map(item => [item.id, item.label]));
const REASON_LABEL = {repair: "Ремонт", replacement: "Замена оборудования", passport: "Паспортные данные", inspection: "Обследование", correction: "Исправление записи"};
const EVIDENCE_LABEL = {documented: "Документировано", estimate: "Оценка специалиста"};
const SOURCE_LABEL: Record<string, string> = {kind: "Тип источника", reference: "Документ / ссылка", model: "Модель насоса", speed_rpm: "Обороты, об/мин", frequency_hz: "Частота, Гц", verified: "Применимость подтверждена", note: "Примечание"};
const emptyMeta = (): MetaDraft => ({effective_at: "", reason: "repair", evidence: "estimate", source: "", author: "", comment: ""});
const numberFormat = new Intl.NumberFormat("ru-RU", {maximumSignificantDigits: 21});

function parameterTitle(parameter: EquipmentParameter | undefined, fallback = "") {
  return parameter ? `${parameter.name}${parameter.symbol ? ` (${parameter.symbol})` : ""}${parameter.unit ? `, ${parameter.unit}` : ""}` : fallback;
}
function displayValue(value: unknown): string {
  if (value == null || value === "") return "Не указано";
  if (typeof value === "number") return numberFormat.format(value);
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  if (Array.isArray(value)) return value.length ? value.map(point => Array.isArray(point) ? `(${point.map(displayValue).join("; ")})` : displayValue(point)).join(", ") : "Нет точек";
  if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${SOURCE_LABEL[key] ?? key}: ${displayValue(item)}`).join("; ");
  return String(value);
}
function requestError(payload: {detail?: unknown} | null, fallback: string): string {
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail)) return payload.detail.map((item: {loc?: (string | number)[]; msg?: string}) => `${item.loc?.slice(1).join(".") ?? ""}: ${item.msg ?? "Некорректное значение"}`).join("; ");
  return fallback;
}
function equipmentValue(view: EquipmentResponse | undefined, key: string): unknown {
  if (!view) return null;
  if (view.provenance?.field_sources?.[key]?.reset) return key === "pump.curve_qh" || key === "pump.curve_qeta" ? [] : null;
  if (key === "vfd") return view.equipment.vfd;
  const [part, field] = key.split(".");
  const node = view.equipment[part as "pump" | "motor" | "transmission"];
  return node?.[field as keyof typeof node] ?? null;
}
function sourceDraft(value: unknown): SourceDraft {
  const source = value as PumpCurveSource | null;
  return {kind: source?.kind ?? "unverified", reference: source?.reference ?? "", model: source?.model ?? "", speed_rpm: source?.speed_rpm == null ? "" : String(source.speed_rpm), frequency_hz: source?.frequency_hz == null ? "" : String(source.frequency_hz), verified: source?.verified ?? false, note: source?.note ?? ""};
}
function curveRows(value: unknown): CurveRow[] {
  return Array.isArray(value) ? value.map(([q, ordinate]: [number, number]) => [String(q), String(ordinate)]) : [];
}
function parseCurve(rows: CurveRow[], parameter: EquipmentParameter, errors: string[]): number[][] {
  const points: number[][] = [], seen = new Set<number>();
  for (const [qRaw, valueRaw] of rows) {
    if (!qRaw.trim() && !valueRaw.trim()) continue;
    const q = parseEquipmentNumber(qRaw), value = parseEquipmentNumber(valueRaw);
    if (q == null || value == null || !Number.isFinite(q) || !Number.isFinite(value) || q < 0 || value < 0 || (parameter.kind === "curve_qeta" && value > 1) || seen.has(q)) {
      errors.push(`${parameter.name}: нужны уникальные неотрицательные подачи и конечные значения${parameter.kind === "curve_qeta" ? " КПД от 0 до 1" : ""}`);
    } else { seen.add(q); points.push([q, value]); }
  }
  return points;
}
function CurveTable({rows, parameter, onChange}: {rows: CurveRow[]; parameter: EquipmentParameter; onChange: (rows: CurveRow[]) => void}) {
  const update = (index: number, column: 0 | 1, value: string) => onChange(rows.map((row, i) => i === index ? column === 0 ? [value, row[1]] : [row[0], value] : row));
  return <div className="curve-editor"><table><thead><tr><th>Подача Q, м³/ч</th><th>{parameter.kind === "curve_qh" ? "Напор H, м" : "КПД η, доля"}</th><th></th></tr></thead><tbody>
    {rows.map((row, index) => <tr key={index}><td><input aria-label={`${parameter.name}: подача точки ${index + 1}`} value={row[0]} onChange={event => update(index, 0, event.target.value)}/></td>
      <td><input aria-label={`${parameter.name}: значение точки ${index + 1}`} value={row[1]} onChange={event => update(index, 1, event.target.value)}/></td>
      <td><Button variant="secondary" aria-label={`${parameter.name}: удалить точку ${index + 1}`} onClick={() => onChange(rows.filter((_, i) => i !== index))}>Удалить</Button></td></tr>)}
  </tbody></table><Button variant="secondary" onClick={() => onChange([...rows, ["", ""]])}>Добавить точку</Button></div>;
}

function JournalEditor({p}: {p: Props}) {
  const base = `/objects/${segment(p.objectId)}/aggregates/${segment(p.aggregateId)}`;
  const ready = Boolean(p.objectId && p.aggregateId && !p.selectionPending);
  const journal = useResource<EquipmentJournalResponse>(ready ? `${base}/equipment-journal` : null, undefined, true);
  const [component, setComponent] = useState<Component>("pump");
  const [values, setValues] = useState<Record<string, string>>({});
  const [curves, setCurves] = useState<Partial<Record<CurveKey, CurveRow[]>>>({});
  const [source, setSource] = useState<SourceDraft | null | undefined>(undefined);
  const [meta, setMeta] = useState<MetaDraft>(emptyMeta);
  const [supersedes, setSupersedes] = useState<JournalEntry | null>(null);
  const [revision, setRevision] = useState("");
  const [conflict, setConflict] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{kind: "error" | "ok"; text: string} | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const dialog = useRef<HTMLDialogElement>(null), saveButton = useRef<HTMLButtonElement>(null), root = useRef<HTMLDivElement>(null);
  const baseline = useResource<EquipmentResponse>(ready ? `${base}/equipment${meta.effective_at ? `?at=${encodeURIComponent(meta.effective_at)}` : ""}` : null, undefined, true);
  const parameters = journal.data?.parameters;
  const byKey = useMemo(() => Object.fromEntries((parameters ?? []).map(item => [item.key, item])), [parameters]);
  const componentParameters = (parameters ?? []).filter(item => item.component === component);
  const editable = componentParameters.filter(item => !supersedes || Object.hasOwn(supersedes.changes, item.key));
  const replacement = !supersedes && meta.reason === "replacement";
  const focusKey = new URL(location.href).searchParams.get("focus") ?? "";
  const label = (key: string) => parameterTitle(byKey[key], key);
  const beforeValue = (key: string) => supersedes ? supersedes.changes[key] ?? null : equipmentValue(baseline.data, key);
  const inputBase = (key: string) => replacement ? null : beforeValue(key);
  const rawValue = (key: string) => Object.hasOwn(values, key) ? values[key] : inputBase(key) == null ? "" : String(inputBase(key));
  const currentSource = source === undefined ? sourceDraft(inputBase("pump.curve_source")) : source ?? sourceDraft(null);
  const patchSource = (patch: Partial<SourceDraft>) => setSource({...currentSource, ...patch});

  useEffect(() => { if (journal.data && !revision) setRevision(journal.data.revision); }, [journal.data, revision]);
  useEffect(() => { const target = focusKey.split(".")[0]; if (COMPONENTS.some(item => item.id === target)) setComponent(target as Component); }, [focusKey]);
  useEffect(() => { root.current?.querySelector<HTMLElement>('[data-focused="true"]')?.scrollIntoView({block: "center"}); }, [component, focusKey]);
  useEffect(() => {
    if (confirmation && !dialog.current?.open) dialog.current?.showModal();
    else if (!confirmation && dialog.current?.open) dialog.current.close();
  }, [confirmation]);

  const resetDraft = () => { setValues({}); setCurves({}); setSource(undefined); setSupersedes(null); };
  const changeReason = (reason: MetaDraft["reason"]) => {
    if ((reason === "replacement") !== replacement) { setValues({}); setCurves({}); setSource(undefined); }
    setMeta(previous => ({...previous, reason}));
  };
  const collectCandidate = () => {
    const candidate: Record<string, unknown> = {}, before: Record<string, unknown> = {}, errors: string[] = [];
    for (const parameter of editable) {
      const key = parameter.key, previous = beforeValue(key);
      before[key] = previous;
      if (parameter.kind === "curve_qh" || parameter.kind === "curve_qeta") {
        candidate[key] = parseCurve(curves[key as CurveKey] ?? curveRows(inputBase(key)), parameter, errors);
      } else if (parameter.kind === "curve_source") {
        if (source === undefined) candidate[key] = inputBase(key);
        else if (source === null) candidate[key] = null;
        else {
          const numeric = (text: string, name: string) => {
            const number = parseEquipmentNumber(text);
            if (number != null && (!Number.isFinite(number) || number <= 0)) errors.push(`${name}: нужно положительное конечное число`);
            return number;
          };
          const record: PumpCurveSource = {kind: source.kind, reference: source.reference.trim(), model: source.model.trim() || null,
            speed_rpm: numeric(source.speed_rpm, "Обороты кривой"), frequency_hz: numeric(source.frequency_hz, "Частота кривой"), verified: source.verified, note: source.note.trim()};
          if (record.verified && (record.kind === "unverified" || !record.reference || !record.model || record.speed_rpm == null)) errors.push("Подтверждение кривой требует источника, модели и оборотов");
          if (record.verified && meta.evidence === "estimate") errors.push("Оценка специалиста не подтверждает применимость кривой");
          candidate[key] = record.kind === "unverified" && !record.reference && !record.model && record.speed_rpm == null && record.frequency_hz == null && !record.verified && !record.note ? null : record;
        }
        if (supersedes && meta.evidence === "estimate" && candidate[key] != null) candidate[key] = {...candidate[key] as PumpCurveSource, verified: false};
      } else {
        const raw = rawValue(key);
        let value: unknown = raw;
        if (parameter.kind === "number") value = parseEquipmentNumber(raw);
        else if (parameter.kind === "bool") value = raw === "true" ? true : raw === "false" ? false : null;
        else if (parameter.kind === "select") value = raw || null;
        else value = Object.hasOwn(values, key) ? raw.trim() : raw;
        if (parameter.kind === "text" && key === "transmission.model" && value === "") value = null;
        if (parameter.kind === "number" && value != null && (replacement || !sameParameterValue(previous, value))) {
          const number = value as number;
          if (!Number.isFinite(number) || (parameter.minimum != null && (parameter.exclusive_minimum ? number <= parameter.minimum : number < parameter.minimum)) || (parameter.maximum != null && number > parameter.maximum)) errors.push(`${parameter.name}: значение вне допустимого диапазона`);
        }
        candidate[key] = value;
      }
    }
    return {candidate, before, errors};
  };

  const draft = collectCandidate();
  const reason = supersedes ? "correction" : meta.reason;
  const changes = journalPatch(draft.before, draft.candidate, reason);
  const changedKeys = supersedes ? parameterDifferences(draft.before, draft.candidate).map(row => row.key) : Object.keys(changes);
  const metadataRows = supersedes ? [
    {key: "effective_at", parameter: "Действует с", before: normalizeEquipmentTime(supersedes.effective_at), after: normalizeEquipmentTime(meta.effective_at)},
    {key: "evidence", parameter: "Подтверждение", before: EVIDENCE_LABEL[supersedes.evidence], after: EVIDENCE_LABEL[meta.evidence]},
    {key: "source", parameter: "Источник данных", before: supersedes.source, after: meta.source.trim()},
    {key: "comment", parameter: "Комментарий", before: supersedes.comment ?? "", after: meta.comment.trim()},
  ].filter(row => row.before !== row.after) : [];
  const hasChanges = draft.errors.length > 0 || (Object.keys(changes).length > 0 && (changedKeys.length > 0 || metadataRows.length > 0));

  const prepareConfirmation = () => {
    if (!baseline.data || baseline.loading || !journal.data || !parameters?.length) { setMessage({kind: "error", text: "Дождитесь загрузки значений на выбранную дату."}); return; }
    const errors = [...draft.errors];
    if (!meta.effective_at) errors.push("Укажите дату действия");
    if (!meta.source.trim() || !meta.author.trim()) errors.push("Укажите источник данных и автора записи");
    if (replacement && (component === "pump" || component === "motor") && !changes[`${component}.model`]) errors.push("Для замены укажите модель нового оборудования");
    if (replacement && component === "pump" && !changes["pump.kind"]) errors.push("Для замены насоса укажите его тип");
    if (errors.length) { setMessage({kind: "error", text: errors.join(". ")}); return; }
    if (!hasChanges) { setMessage({kind: "ok", text: "Изменений нет. Запись в журнал не создаётся."}); return; }
    const rows: SummaryRow[] = (replacement ? Object.keys(draft.candidate) : changedKeys)
      .map(key => ({key, parameter: label(key), before: displayValue(draft.before[key]), after: displayValue(draft.candidate[key])}));
    rows.push(...metadataRows.map(row => ({...row, before: displayValue(row.before), after: displayValue(row.after)})));
    setMessage(null);
    setConfirmation({payload: {component, effective_at: normalizeEquipmentTime(meta.effective_at), expected_revision: revision, changes,
      reason, evidence: meta.evidence, source: meta.source.trim(), author: meta.author.trim(), comment: meta.comment.trim(), supersedes_id: supersedes?.id ?? null}, rows, replacement});
  };

  const publish = async () => {
    if (!confirmation || saving) return;
    const payload = confirmation.payload;
    setSaving(true);
    try {
      const response = await fetch(`/api${base}/equipment-journal`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
      const result = await response.json().catch(() => null);
      setConfirmation(null);
      if (response.status === 409) {
        setConflict(true);
        setMessage({kind: "error", text: `${requestError(result, "Конфликт записи журнала.")} Черновик сохранён. Загрузите актуальный журнал и повторно проверьте сводку изменений.`});
        return;
      }
      if (!response.ok) { setMessage({kind: "error", text: requestError(result, "Не удалось сохранить изменение.")}); return; }
      setRevision((result as EquipmentJournalResponse).revision);
      resetDraft();
      setMeta(previous => ({...emptyMeta(), author: previous.author}));
      setConflict(false);
      p.onEquipmentOverride(null);
      invalidateResources();
      setMessage({kind: "ok", text: "Изменение сохранено в журнале. Расчёты обновлены с учётом даты действия."});
    } catch { setConfirmation(null); setMessage({kind: "error", text: "Не удалось сохранить изменение. Черновик сохранён; проверьте соединение."}); }
    finally { setSaving(false); }
  };
  const reloadJournal = async () => {
    try {
      const response = await fetch(`/api${base}/equipment-journal`);
      if (!response.ok) throw new Error("Не удалось загрузить журнал");
      const latest = await response.json() as EquipmentJournalResponse;
      setRevision(latest.revision); setConflict(false); setConfirmation(null);
      if (supersedes && !latest.items.some(entry => entry.id === supersedes.id && entry.superseded_by == null)) {
        setMessage({kind: "error", text: "Исходная запись уже исправлена. Черновик сохранён: выберите актуальную запись в журнале для исправления."});
        setConflict(true);
      } else setMessage({kind: "ok", text: "Актуальный журнал загружен. Черновик сохранён; перед публикацией ещё раз проверьте сводку."});
      invalidateResources();
    } catch (error) { setMessage({kind: "error", text: error instanceof Error ? error.message : "Не удалось загрузить журнал"}); }
  };
  const startCorrection = (entry: JournalEntry) => {
    resetDraft(); setSupersedes(entry); setComponent(entry.component);
    if (journal.data) setRevision(journal.data.revision);
    setMeta(previous => ({...previous, effective_at: entry.effective_at, reason: "correction", evidence: entry.evidence, source: entry.source, comment: entry.comment ?? ""}));
    setConflict(false); setConfirmation(null);
    setMessage({kind: "ok", text: `Исправление записи №${entry.id}. Её исходные значения загружены в поля; прежняя запись останется в истории.`});
    root.current?.scrollIntoView({block: "start"});
  };
  const fieldRow = (parameter: EquipmentParameter) => {
    const known = inputBase(parameter.key) != null;
    return <label className="manual-field" key={parameter.key} data-focused={focusKey === parameter.key || undefined}>
      <span>{parameterTitle(parameter)}</span>
      {parameter.kind === "bool" ? <select value={rawValue(parameter.key)} onChange={event => setValues(previous => ({...previous, [parameter.key]: event.target.value}))}>
        <option value="" disabled={known && !replacement}>Не указано</option><option value="true">Да</option><option value="false">Нет</option>
      </select> : parameter.kind === "select" ? <select value={rawValue(parameter.key)} onChange={event => setValues(previous => ({...previous, [parameter.key]: event.target.value}))}>
        <option value="" disabled={known && !replacement}>Не указано</option>{parameter.options?.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select> : <input inputMode={parameter.kind === "number" ? "decimal" : undefined} value={rawValue(parameter.key)} placeholder="Не указано"
        onChange={event => setValues(previous => ({...previous, [parameter.key]: event.target.value}))}/>}</label>;
  };
  const items = journal.data?.items ?? [], legacy = journal.data?.legacy_history ?? [];
  const sourceParameter = editable.find(parameter => parameter.kind === "curve_source");

  return <div ref={root}><Panel title="Характеристики оборудования" caption="В полях показаны действующие значения. Измените нужные параметры и нажмите «Сохранить»: перед записью откроется сводка «было → стало».">
    <Status {...journal} empty={ready ? "Журнал недоступен." : "Выберите объект и агрегат."}/>
    {message && <p className={`notice ${message.kind === "error" ? "error" : ""}`} role={message.kind === "error" ? "alert" : "status"}>{message.text}</p>}
    {conflict && <Button variant="secondary" onClick={() => void reloadJournal()}>Загрузить актуальный журнал и перепроверить черновик</Button>}
    {p.equipmentOverride && <p className="notice">Действует временный сценарий. <Button variant="secondary" onClick={() => p.onEquipmentOverride(null)}>Убрать сценарий</Button></p>}
    {supersedes && <p className="notice">Исправляется запись №{supersedes.id}. <Button variant="secondary" onClick={() => {resetDraft(); setMeta(previous => ({...previous, reason: "repair"}));}}>Отменить исправление</Button></p>}
    {ready && parameters?.length ? <form className="manual-form" onSubmit={event => {event.preventDefault(); prepareConfirmation();}}>
      <label className="manual-field"><span>Компонент изменения</span><select value={component} disabled={Boolean(supersedes)} onChange={event => {resetDraft(); setComponent(event.target.value as Component);}}>{COMPONENTS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      {baseline.loading && <p role="status">Загружаем значения на выбранную дату…</p>}
      {baseline.error && <p role="alert" className="notice error">{baseline.error}</p>}
      {replacement && <p className="notice">При замене заполняются характеристики нового узла, а не копируются данные прежнего. Неуказанные параметры станут неизвестными; это будет показано в подтверждении.</p>}
      <fieldset className="journal-fields" disabled={baseline.loading || !baseline.data}><legend>Параметры</legend><div className="manual-grid">
        {editable.filter(parameter => ["text", "number", "bool", "select"].includes(parameter.kind)).map(fieldRow)}
      </div>
      {component === "pump" && <p className="muted">Номинальный КПД и характеристика Q–η — не мгновенный измеренный КПД режима. Изменение исполнения, оборотов или кривых снимает прежнее подтверждение их применимости.</p>}
      {editable.filter(parameter => parameter.kind === "curve_qh" || parameter.kind === "curve_qeta").map(parameter => <details key={parameter.key} open={focusKey === parameter.key || undefined}>
        <summary>{parameterTitle(parameter)}</summary><CurveTable parameter={parameter} rows={curves[parameter.key as CurveKey] ?? curveRows(inputBase(parameter.key))}
          onChange={rows => setCurves(previous => ({...previous, [parameter.key]: rows}))}/>
      </details>)}
      {sourceParameter && <details open={focusKey.startsWith("pump.curve_source") || undefined}><summary>{parameterTitle(sourceParameter)}</summary><div className="manual-grid">
        <label><span>Тип источника</span><select value={currentSource.kind} onChange={event => patchSource({kind: event.target.value as PumpCurveSource["kind"], verified: false})}>
          <option value="unverified">Не подтверждён</option><option value="manufacturer">Заводская характеристика</option><option value="engineering">Инженерная оценка</option><option value="experimental">Натурные испытания</option>
        </select></label>
        <label><span>Документ / ссылка</span><input value={currentSource.reference} onChange={event => patchSource({reference: event.target.value})}/></label>
        <label><span>Модель насоса кривой</span><input value={currentSource.model} onChange={event => patchSource({model: event.target.value, verified: false})}/></label>
        <label><span>Частота вращения кривой, об/мин</span><input value={currentSource.speed_rpm} onChange={event => patchSource({speed_rpm: event.target.value, verified: false})}/></label>
        <label><span>Частота сети, Гц</span><input value={currentSource.frequency_hz} onChange={event => patchSource({frequency_hz: event.target.value, verified: false})}/></label>
        <label><span>Примечание</span><input value={currentSource.note} onChange={event => patchSource({note: event.target.value})}/></label>
        <label className="manual-check"><input type="checkbox" checked={currentSource.verified} onChange={event => patchSource({verified: event.target.checked})}/>Применимость подтверждена</label>
        <Button variant="secondary" onClick={() => setSource(null)}>Очистить сведения об источнике кривых</Button>
      </div></details>}
      </fieldset>
      <fieldset className="manual-provenance"><legend>Основание записи</legend>
        <label><span>Действует с *</span><input type="datetime-local" step="any" required value={meta.effective_at} onChange={event => setMeta(previous => ({...previous, effective_at: event.target.value}))}/></label>
        <label><span>Основание</span><select value={supersedes ? "correction" : meta.reason} disabled={Boolean(supersedes)} onChange={event => changeReason(event.target.value as MetaDraft["reason"])}>
          {Object.entries(REASON_LABEL).filter(([key]) => key !== "correction" || supersedes).map(([key, text]) => <option key={key} value={key}>{text}</option>)}
        </select></label>
        <label><span>Подтверждение</span><select value={meta.evidence} onChange={event => setMeta(previous => ({...previous, evidence: event.target.value as MetaDraft["evidence"]}))}>{Object.entries(EVIDENCE_LABEL).map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>
        <label><span>Источник данных *</span><input required value={meta.source} onChange={event => setMeta(previous => ({...previous, source: event.target.value}))}/></label>
        <label><span>Автор записи *</span><input required value={meta.author} onChange={event => setMeta(previous => ({...previous, author: event.target.value}))}/></label>
        <label><span>Комментарий</span><input value={meta.comment} onChange={event => setMeta(previous => ({...previous, comment: event.target.value}))}/></label>
        <p className="muted">Дата действия — момент изменения оборудования, а не дата ввода записи. Пустое числовое поле означает неизвестное значение. Оценка специалиста остаётся допущением.</p>
      </fieldset>
      <div className="manual-actions">
        <button ref={saveButton} className="ds-button ds-button-primary" type="submit" aria-describedby="journal-save-status" disabled={!hasChanges || conflict || saving || baseline.loading || !baseline.data}>Сохранить</button>
        <span id="journal-save-status" className="muted" role="status">{baseline.loading ? "Загружаем значения…" : hasChanges ? "Есть несохранённые изменения" : replacement ? "Укажите характеристики нового оборудования" : "Нет изменений для сохранения"}</span>
      </div>
    </form> : null}
    <dialog ref={dialog} className="journal-confirmation" aria-labelledby="journal-confirm-title" onCancel={event => {if (saving) event.preventDefault();}} onClose={() => {setConfirmation(null); saveButton.current?.focus();}}>
      {confirmation && <><h2 id="journal-confirm-title">Подтверждение изменения характеристик</h2>
        <p>{COMPONENT_LABEL[confirmation.payload.component]} · действует с {confirmation.payload.effective_at.replace("T", " ")}</p>
        <h3>{confirmation.replacement ? "Характеристики нового оборудования" : "Изменено"}</h3>
        <Table rows={confirmation.rows} columns={[{key: "parameter", label: "Параметр"}, {key: "before", label: "Было"}, {key: "after", label: "Стало"}]}/>
        <p className="muted">{EVIDENCE_LABEL[confirmation.payload.evidence]} · {confirmation.payload.source} · автор: {confirmation.payload.author}</p>
        {confirmation.replacement && <p className="notice">Это замена узла. Незаданные характеристики прежнего оборудования не наследуются, даже если модель совпадает.</p>}
        <div className="manual-actions"><button type="button" className="ds-button ds-button-secondary" autoFocus disabled={saving} onClick={() => setConfirmation(null)}>Продолжить редактирование</button>
          <Button loading={saving} disabled={saving} onClick={() => void publish()}>Подтвердить и сохранить</Button></div>
      </>}
    </dialog>
    {baseline.data?.provenance?.field_sources && <details><summary>Источники текущих характеристик</summary>
      <Table rows={Object.entries(baseline.data.provenance.field_sources).map(([key, origin]) => ({
        parameter: label(key), value: origin.reset ? "Неизвестно после замены" : displayValue(equipmentValue(baseline.data, key)),
        effective: origin.effective_at?.replace("T", " ") ?? "—", evidence: origin.reset ? "Не подтверждено" : origin.evidence ? EVIDENCE_LABEL[origin.evidence] : "Архив паспорта",
        source: origin.source, author: origin.author, recorded: origin.recorded_at, entry: origin.journal_id ?? "—",
      }))} columns={[{key: "parameter", label: "Характеристика"}, {key: "value", label: "Значение"}, {key: "effective", label: "Действует с"}, {key: "evidence", label: "Подтверждение"}, {key: "source", label: "Источник"}, {key: "author", label: "Автор"}, {key: "recorded", label: "Записана"}, {key: "entry", label: "Запись №"}]}/>
    </details>}
  </Panel>
  <Panel title="Журнал изменений" caption="Дата действия и время записи учитываются отдельно. Исходные записи сохраняются при исправлении.">
    {!items.length && !journal.loading && <p className="muted">Записей журнала пока нет.</p>}
    {items.length > 0 && <Table rows={items.map(entry => ({id: entry.id, effective: entry.effective_at.replace("T", " "), recorded: new Date(entry.recorded_at).toLocaleString("ru-RU"), component: COMPONENT_LABEL[entry.component],
      changes: [...Object.entries(entry.changes).map(([key, value]) => `${label(key)}: ${displayValue(value)}`), ...Object.keys(entry.resets).map(key => `${label(key)}: неизвестно после замены`)].join("; "),
      reason: REASON_LABEL[entry.reason], evidence: EVIDENCE_LABEL[entry.evidence], source: entry.source, author: entry.author, comment: entry.comment,
      state: entry.superseded_by != null ? `Заменена записью №${entry.superseded_by}` : entry.supersedes_id != null ? `Исправляет №${entry.supersedes_id}` : "Не исправлена", entry,
    }))} columns={[{key: "id", label: "№"}, {key: "effective", label: "Действует с"}, {key: "recorded", label: "Записана"}, {key: "component", label: "Узел"}, {key: "changes", label: "Характеристики"}, {key: "reason", label: "Основание"}, {key: "evidence", label: "Подтверждение"}, {key: "source", label: "Источник"}, {key: "author", label: "Автор"}, {key: "comment", label: "Комментарий"}, {key: "state", label: "Состояние"},
      {key: "action", label: "", render: row => {const entry = row.entry as JournalEntry; return entry.superseded_by == null ? <Button variant="secondary" onClick={() => startCorrection(entry)}>Исправить</Button> : null;}},
    ]}/>}
    {legacy.length > 0 && <details><summary>Архив прежних редакций паспорта ({legacy.length})</summary><Table rows={legacy.map(entry => ({...entry, from: entry.valid_from.replace("T", " "), until: entry.valid_to?.replace("T", " ") ?? "—"}))}
      columns={[{key: "from", label: "Действует с"}, {key: "until", label: "Действует до"}, {key: "revision", label: "Редакция"}, {key: "source", label: "Источник"}, {key: "author", label: "Автор записи"}, {key: "comment", label: "Комментарий"}]}/></details>}
  </Panel></div>;
}

function ArchivedMeasurements({p}: {p: Props}) {
  const resource = useResource<{items: ManualMeasurement[]}>(p.objectId && p.aggregateId ? `/objects/${segment(p.objectId)}/aggregates/${segment(p.aggregateId)}/manual-measurements` : null, undefined, true);
  const items = resource.data?.items ?? [];
  if (!items.length) return null;
  return <Panel title="Архивные ручные замеры" caption="Ранее сохранённые записи. Новые замеры здесь не вводятся и автоматически не выбираются.">
    <label><span>Выездной замер</span><select aria-label="Выездной замер" value={p.measurementId ?? ""} onChange={event => p.onSelectMeasurement(event.target.value ? Number(event.target.value) : null)}>
      <option value="">Исходный выездной замер (если предоставлен)</option>{items.map(item => <option key={item.id} value={item.id}>№{item.id} · {item.measured_at.replace("T", " ")} · {item.source}</option>)}
    </select></label>
    {p.source !== "field_trip" && <p className="muted">Выбор архивной записи переведёт расчёт в режим «Выезд».</p>}
  </Panel>;
}
export function EquipmentJournalPage(p: Props) { return <><JournalEditor key={`${p.objectId}/${p.aggregateId}`} p={p}/><ArchivedMeasurements p={p}/></>; }
