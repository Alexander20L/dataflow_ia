"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ListChecks,
  LoaderCircle,
  Save,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ApiError, errorMessage } from "@/lib/api";
import { useApp } from "@/lib/providers";
import { useUnsavedGuard } from "@/lib/use-unsaved-guard";
import { useRepresentations } from "@/features/executions/api";
import { useSemanticHistory } from "@/features/understanding/api";
import { OperationPicker } from "./operation-picker";
import { ParameterForm, type ColumnOption } from "./parameter-form";
import { PlanSummary } from "./plan-summary";
import {
  draftOf,
  nextStepId,
  useApplicableOperations,
  useCreatePlan,
  useExecutePlan,
  useOperations,
  useProjectPlans,
  useRevisePlan,
  type Operation,
  type Plan,
  type PlanDraft,
  type PlanStep,
} from "./api";

type Table = NonNullable<ReturnType<typeof useRepresentations>["data"]>[number];
type Props = {
  projectId: string;
  versionId: string;
  archived: boolean;
  onDirtyChange: (dirty: boolean) => void;
  onOpenUnderstanding: () => void;
  onExecuted: (executionId: string) => void;
};
const NEW = "new";

export function PlanEditor(props: Props) {
  const { projectId, versionId, onDirtyChange } = props;
  const plans = useProjectPlans(projectId);
  const tables = useRepresentations(versionId);
  const operations = useOperations();
  const [family, setFamily] = useState<string | null>(null);
  const [epoch, setEpoch] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const versionPlans = useMemo(
    () =>
      plans.data?.items.filter((plan) => plan.input.version_id === versionId) ??
      [],
    [plans.data, versionId],
  );
  const selected = family ?? versionPlans[0]?.family_id ?? NEW;
  const plan = versionPlans.find((item) => item.family_id === selected) ?? null;

  function markDirty(value: boolean) {
    setDirty(value);
    onDirtyChange(value);
  }
  function choose(next: string) {
    setFamily(next);
    setEpoch((value) => value + 1);
    markDirty(false);
  }
  if (plans.isPending || tables.isPending || operations.isPending)
    return (
      <p className="empty-copy" role="status">
        Cargando planes y catálogo…
      </p>
    );
  const error = plans.error ?? tables.error ?? operations.error;
  if (error)
    return (
      <div className="empty-state compact">
        <p role="alert">{errorMessage(error)}</p>
        <Button
          onClick={() => {
            void plans.refetch();
            void tables.refetch();
            void operations.refetch();
          }}
        >
          Reintentar
        </Button>
      </div>
    );
  return (
    <div className="plan-editor">
      <div className="dataset-controls">
        <label htmlFor="plan-select">
          <ListChecks size={14} />
          Plan
        </label>
        <select
          id="plan-select"
          value={selected}
          onChange={(e) =>
            dirty ? setPending(e.target.value) : choose(e.target.value)
          }
        >
          {versionPlans.map((item) => (
            <option key={item.family_id} value={item.family_id}>
              Plan {item.family_id.slice(0, 8)} · revisión {item.revision} ·{" "}
              {item.validation.valid ? "válido" : "incompleto"}
            </option>
          ))}
          <option value={NEW}>Nuevo plan…</option>
        </select>
      </div>
      <PlanForm
        // Remonta al cambiar de plan, descartar, o cuando aparece el plan recién creado.
        key={`${selected}-${epoch}-${plan ? "saved" : "draft"}`}
        {...props}
        plan={plan}
        tables={tables.data ?? []}
        operations={operations.data?.operations ?? []}
        onDirty={markDirty}
        onCreated={(created) => {
          setFamily(created.family_id);
          markDirty(false);
        }}
      />
      {pending && (
        <Dialog
          title="Hay cambios sin guardar en el plan"
          onClose={() => setPending(null)}
        >
          <p className="dialog-copy">
            Si cambias de plan se descartará el borrador. Las revisiones
            guardadas no se alteran.
          </p>
          <div className="form-footer">
            <Button variant="ghost" onClick={() => setPending(null)}>
              Seguir editando
            </Button>
            <Button
              onClick={() => {
                choose(pending);
                setPending(null);
              }}
            >
              Descartar y cambiar
            </Button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

function PlanForm({
  projectId,
  versionId,
  archived,
  plan,
  tables,
  operations,
  onDirty,
  onCreated,
  onOpenUnderstanding,
  onExecuted,
}: Props & {
  plan: Plan | null;
  tables: Table[];
  operations: Operation[];
  onDirty: (dirty: boolean) => void;
  onCreated: (plan: Plan) => void;
}) {
  const [tableId, setTableId] = useState(
    plan?.input.artifact_id ?? tables[0]?.id ?? "",
  );
  const [draft, setDraft] = useState<PlanDraft>(() => draftOf(plan));
  const [baseline, setBaseline] = useState(() => JSON.stringify(draftOf(plan)));
  const [expected, setExpected] = useState(plan?.head_revision ?? 0);
  const [reset, setReset] = useState(false);
  const router = useRouter();
  const { notify } = useApp();
  const create = useCreatePlan(projectId);
  const revise = useRevisePlan(projectId);
  const execute = useExecutePlan(versionId);
  const table = tables.find((item) => item.id === tableId);
  const semantics = useSemanticHistory(tableId || undefined);
  const applicable = useApplicableOperations(
    tableId || undefined,
    draft.semantic_ref?.id,
  );
  const dirty = JSON.stringify(draft) !== baseline;
  const newer = !!plan && plan.head_revision !== expected;
  const [route, setRoute] = useUnsavedGuard(dirty);
  const columns: ColumnOption[] = (table?.columns ?? []).map((column) => ({
    id: String(column.id),
    name: String(column.name),
  }));
  const saving = create.isPending || revise.isPending;
  const readOnly = archived || saving;

  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  function update(steps: PlanStep[]) {
    setDraft({ ...draft, steps });
  }
  function load(value: Plan) {
    const next = draftOf(value);
    setDraft(next);
    setBaseline(JSON.stringify(next));
    setExpected(value.head_revision);
    setReset(false);
    revise.reset();
  }
  function goToStep(stepId: string | null) {
    const target = document.getElementById(
      stepId ? `plan-step-${stepId}` : "plan-catalog",
    );
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
    target?.focus();
  }
  async function save() {
    try {
      if (!plan) {
        if (!table) return;
        const created = await create.mutateAsync({
          table_artifact_id: table.id,
          table_sha256: table.sha256,
          semantic_ref: draft.semantic_ref,
          steps: draft.steps,
        });
        notify(`Plan guardado como revisión ${created.revision}.`);
        onCreated(created);
      } else {
        const saved = await revise.mutateAsync({
          familyId: plan.family_id,
          body: {
            expected_revision: expected,
            semantic_ref: draft.semantic_ref,
            steps: draft.steps,
          },
        });
        load(saved);
        notify(`Plan guardado como revisión ${saved.revision}.`);
      }
    } catch {
      /* Error visible; el borrador se conserva. */
    }
  }
  const conflict =
    revise.error instanceof ApiError && revise.error.status === 409;
  return (
    <section className="plan-form" aria-label="Editor de plan">
      <div className="semantic-status">
        <span className="badge neutral">
          {plan ? `Revisión ${expected} guardada` : "Plan nuevo sin guardar"}
        </span>
        {dirty && <span className="badge review">Cambios sin guardar</span>}
      </div>
      {(newer || conflict) && plan && (
        <div className="warning-banner" role="status">
          <span>
            El servidor tiene la revisión {plan.head_revision}; estás editando
            la {expected}. No se sobrescribirán cambios.
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => (dirty ? setReset(true) : load(plan))}
          >
            Cargar revisión actual
          </Button>
        </div>
      )}
      {archived && (
        <div className="info-banner">
          <span>
            Proyecto archivado: puedes consultar planes, pero no guardarlos ni
            ejecutarlos.
          </span>
        </div>
      )}
      <div className="analysis-controls">
        <div>
          <label htmlFor="plan-table">Tabla de entrada fijada</label>
          <select
            id="plan-table"
            value={tableId}
            disabled={!!plan || readOnly}
            title={
              plan ? "La entrada de un plan guardado no cambia." : undefined
            }
            onChange={(e) => {
              setTableId(e.target.value);
              setDraft({ ...draft, semantic_ref: null });
            }}
          >
            {plan && !table && (
              <option value={tableId}>{tableId.slice(0, 8)} · histórica</option>
            )}
            {tables.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id.slice(0, 8)} · SHA {item.sha256.slice(0, 10)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="plan-semantics">Revisión semántica (opcional)</label>
          <select
            id="plan-semantics"
            value={draft.semantic_ref?.id ?? ""}
            disabled={readOnly || semantics.isPending}
            onChange={(e) => {
              const item = semantics.data?.items.find(
                (revision) => revision.id === e.target.value,
              );
              setDraft({
                ...draft,
                semantic_ref: item
                  ? {
                      id: item.id,
                      revision: item.revision,
                      content_sha256: item.content_sha256,
                    }
                  : null,
              });
            }}
          >
            <option value="">Sin contrato · análisis técnico</option>
            {draft.semantic_ref &&
              !semantics.data?.items.some(
                (item) => item.id === draft.semantic_ref?.id,
              ) && (
                <option value={draft.semantic_ref.id}>
                  Revisión {draft.semantic_ref.revision} · fijada
                </option>
              )}
            {semantics.data?.items.map((item) => (
              <option key={item.id} value={item.id}>
                Revisión {item.revision} · {item.content_sha256.slice(0, 10)}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="plan-layout">
        <div>
          <h4>Pasos del plan</h4>
          {!draft.steps.length && (
            <p className="empty-copy">
              Sin pasos. Añade operaciones desde el catálogo.
            </p>
          )}
          <ol className="plan-steps">
            {draft.steps.map((step, index) => {
              const operation = operations.find(
                (item) =>
                  item.name === step.operation && item.version === step.version,
              );
              const sources = draft.steps
                .slice(0, index)
                .filter(
                  (prior) =>
                    operations.find(
                      (item) =>
                        item.name === prior.operation &&
                        item.version === prior.version,
                    )?.output_kind === "table",
                );
              const source =
                step.input.kind === "step" ? step.input.step_id : "";
              return (
                <li
                  key={`${step.id}-${index}`}
                  id={`plan-step-${step.id}`}
                  tabIndex={-1}
                  className="plan-step"
                  aria-label={`Paso ${step.id}`}
                >
                  <div className="plan-step-heading">
                    <strong>
                      {index + 1}. {operation?.title ?? step.operation}
                    </strong>
                    <small className="mono">
                      {step.id} · {step.operation}@{step.version}
                    </small>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={readOnly}
                      aria-label={`Quitar paso ${step.id}`}
                      onClick={() =>
                        update(draft.steps.filter((_, i) => i !== index))
                      }
                    >
                      <Trash2 size={14} />
                    </Button>
                  </div>
                  <div className="parameter-field">
                    <label htmlFor={`plan-step-${step.id}-input`}>
                      Entrada
                    </label>
                    <select
                      id={`plan-step-${step.id}-input`}
                      disabled={readOnly}
                      value={source}
                      onChange={(e) =>
                        update(
                          draft.steps.map((item, i) =>
                            i === index
                              ? {
                                  ...item,
                                  input: e.target.value
                                    ? { kind: "step", step_id: e.target.value }
                                    : { kind: "input", alias: "source" },
                                }
                              : item,
                          ),
                        )
                      }
                    >
                      <option value="">Tabla de entrada fijada</option>
                      {source &&
                        !sources.some((prior) => prior.id === source) && (
                          <option value={source}>
                            Paso {source} (no válido)
                          </option>
                        )}
                      {sources.map((prior) => (
                        <option key={prior.id} value={prior.id}>
                          Salida del paso {prior.id}
                        </option>
                      ))}
                    </select>
                  </div>
                  {operation ? (
                    <ParameterForm
                      schema={operation.parameters_schema}
                      value={step.parameters ?? {}}
                      columns={columns}
                      idPrefix={`plan-step-${step.id}`}
                      disabled={readOnly}
                      onChange={(parameters) =>
                        update(
                          draft.steps.map((item, i) =>
                            i === index ? { ...item, parameters } : item,
                          ),
                        )
                      }
                    />
                  ) : (
                    <p className="auth-error">
                      Operación fuera del catálogo actual.
                    </p>
                  )}
                </li>
              );
            })}
          </ol>
        </div>
        <div id="plan-catalog" tabIndex={-1}>
          <h4>Catálogo</h4>
          {applicable.isError && (
            <p className="auth-error" role="alert">
              {errorMessage(applicable.error)}
            </p>
          )}
          <OperationPicker
            operations={operations}
            applicable={applicable.data ?? []}
            disabled={readOnly || !table}
            onAdd={(operation) =>
              update([
                ...draft.steps,
                {
                  id: nextStepId(draft.steps, operation.name),
                  operation: operation.name,
                  version: operation.version,
                  input: { kind: "input", alias: "source" },
                  parameters: {},
                },
              ])
            }
          />
        </div>
      </div>
      {(create.isError || (revise.isError && !conflict)) && (
        <p className="auth-error" role="alert">
          {errorMessage(create.error ?? revise.error)}
        </p>
      )}
      <div className="form-footer">
        <span className="fine-print muted">
          Guardar crea una revisión inmutable; un plan incompleto se guarda pero
          no se ejecuta.
        </span>
        <Button
          disabled={archived || saving || newer || !table || (!!plan && !dirty)}
          onClick={() => void save()}
        >
          <Save size={16} />
          {saving ? "Guardando…" : "Guardar plan"}
        </Button>
      </div>
      {plan ? (
        <>
          <PlanSummary
            plan={plan}
            dirty={dirty}
            onGoToStep={goToStep}
            onOpenUnderstanding={onOpenUnderstanding}
          />
          {execute.isError && (
            <p className="auth-error" role="alert">
              {errorMessage(execute.error)}
            </p>
          )}
          <div className="form-footer">
            <span className="fine-print muted">
              Se ejecuta la revisión {plan.revision} guardada sobre su tabla
              fijada.
            </span>
            <Button
              disabled={
                archived ||
                dirty ||
                newer ||
                !plan.validation.valid ||
                execute.isPending
              }
              title={
                !plan.validation.valid
                  ? "Resuelve los problemas pendientes para ejecutar."
                  : dirty
                    ? "Guarda los cambios antes de ejecutar."
                    : undefined
              }
              onClick={async () => {
                try {
                  const run = await execute.mutateAsync(plan.id);
                  onExecuted(run.id);
                  notify(`Plan (revisión ${plan.revision}) encolado.`);
                } catch {
                  /* Error visible. */
                }
              }}
            >
              {execute.isPending ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <ArrowRight size={16} />
              )}
              Ejecutar plan
            </Button>
          </div>
        </>
      ) : (
        <p className="fine-print muted">
          Guarda el plan para validarlo y ver sus requisitos pendientes.
        </p>
      )}
      {reset && plan && (
        <Dialog
          title="¿Cargar la revisión del servidor?"
          onClose={() => setReset(false)}
        >
          <p className="dialog-copy">
            Se descartará el borrador local para cargar la revisión actual. No
            se modificará ninguna revisión guardada.
          </p>
          <div className="form-footer">
            <Button variant="ghost" onClick={() => setReset(false)}>
              Seguir editando
            </Button>
            <Button onClick={() => load(plan)}>Descartar y cargar</Button>
          </div>
        </Dialog>
      )}
      {route && (
        <Dialog
          title="Hay cambios sin guardar en el plan"
          onClose={() => setRoute(null)}
        >
          <p className="dialog-copy">
            Puedes seguir editando o descartar este borrador para salir. Las
            revisiones guardadas se conservan.
          </p>
          <div className="form-footer">
            <Button variant="ghost" onClick={() => setRoute(null)}>
              Seguir editando
            </Button>
            <Button
              onClick={() => {
                onDirty(false);
                router.push(route);
                setRoute(null);
              }}
            >
              Descartar y salir
            </Button>
          </div>
        </Dialog>
      )}
    </section>
  );
}
