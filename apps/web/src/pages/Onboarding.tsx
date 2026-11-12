import { useResource, segment } from "../shared/api";
import { Panel } from "../shared/ui/Panel";
import { Status } from "../shared/ui/Status";
import { LinkButton } from "../shared/ui/Button";
import { contextBody, type PageProps } from "../shared/ui/context";
import { RequirementList } from "../features/manual/requirements";
import type { Requirement } from "../shared/types";

type Requirements = {
  requirements: Requirement[];
  basis: { source: string; at: string };
  notes: string[];
};

export function OnboardingPage(p: PageProps) {
  const base = p.objectId && p.aggregateId
    ? `/objects/${segment(p.objectId)}/aggregates/${segment(p.aggregateId)}` : null;
  const requirements = useResource<Requirements>(
    base ? `${base}/data-requirements` : null,
    contextBody(p, { with_regime: Boolean(p.audit) }),
  );
  const guide = useResource<{ yaml_template: string }>(base ? `${base}/onboarding` : null);
  const journalHref = () => {
    const url = new URL(location.href);
    url.hash = "equipment-journal";
    url.searchParams.delete("edit");
    return url.href;
  };
  return <Panel title="Готовность данных" help="Один и тот же список требований используется здесь и в разборе потерь. Наличие значения, происхождение и подтверждение — разные признаки.">
    <div className="content-actions">
      <LinkButton href={journalHref()}>Открыть журнал оборудования</LinkButton>
    </div>
    <Status {...requirements} empty="Выберите объект и агрегат для проверки данных." />
    {requirements.data && <>
      <p className="muted">{requirements.data.basis.source === "passport"
        ? `Паспорт на ${requirements.data.basis.at.replace("T", " ")}; измеренный режим не проверен.`
        : `Требования выбранного режима на ${requirements.data.basis.at.replace("T", " ")}.`}</p>
      {requirements.data.notes.map((note, i) => <p className="notice" key={i}>{note}</p>)}
      <RequirementList items={requirements.data.requirements}
        caption="Для каждого параметра показано, что известно, на какой расчёт он влияет и что нужно сделать. Ручной ввод сам по себе не подтверждает значение." />
    </>}
    <details className="stage-assumptions"><summary>Подключение нового объекта</summary>
      <p>Начальная регистрация объекта пока выполняется через конфигурацию. После регистрации изменения оборудования ведутся в журнале без правки YAML; ранее сохранённые ручные замеры остаются доступными. Телеметрия подключается отдельно.</p>
      <Status {...guide} />
      {guide.data?.yaml_template && <pre className="template-code">{guide.data.yaml_template}</pre>}
    </details>
  </Panel>;
}
