"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, LoaderCircle, Pencil, ShieldCheck } from "lucide-react";
import type { components } from "@dataflow/api-client";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import { useUnsavedGuard } from "@/lib/use-unsaved-guard";
import { useRepresentations } from "@/features/executions/api";
import type { DatasetVersion, Diagnostic } from "@/features/ingestion/api";
import { useCreatePlan, type PlanStep } from "@/features/planning/api";
import { useUnderstanding } from "@/features/understanding/api";
import { EffectPreview } from "./effect-preview";
import { useCreatePreview } from "./api";

type DataType = "string" | "integer" | "decimal" | "date" | "boolean";
type CastType = Exclude<DataType, "string">;
type Column = {
  id: string;
  name: string;
  type: DataType;
  suggested?: DataType;
  identifier: boolean;
};
type Conversion = { type: CastType; scale: number; confirm: boolean };
type NullKeys = "reject" | "group_nulls";
type Draft = {
  tokens: Record<string, string>; // columna → marcadores separados por comas
  trim: string[];
  cast: Record<string, Conversion>;
  drop: string[];
  dedupe: { enabled: boolean; column_ids: string[]; null_keys: NullKeys };
};
type Semantic = components["schemas"]["SemanticRevision"];
type SemanticRef = { id: string; revision: number; content_sha256: string };

const FORMATS: Record<CastType, string> = {
  integer: "integer_ascii",
  decimal: "decimal_dot",
  date: "iso_date",
  boolean: "boolean_lowercase",
};
const TYPE_LABELS: Record<DataType, string> = {
  string: "Texto",
  integer: "Entero",
  decimal: "Decimal",
  date: "Fecha ISO",
  boolean: "Booleano",
};

export function splitTokens(value: string): string[] {
  return [
    ...new Set(
      value
        .split(",")
        .map((token) => token.trim())
        .filter(Boolean),
    ),
  ];
}

/**
 * Borrador inicial: Q-003 → recortar; Q-001 → excluir nulos; Q-002 → deduplicar filas
 * idénticas (nulos agrupados, como Q-002). Los marcadores de nulo salen de la revisión
 * semántica fijada. No se propone ninguna conversión: sólo se indica el tipo sugerido.
 */
export function initialDraft(
  diagnostic: Diagnostic,
  columns: Column[],
  semantic: Semantic | null,
): Draft {
  const ids = (rule: string) =>
    columns
      .filter((column) =>
        column.type === "string" || rule === "Q-001"
          ? diagnostic.quality.issues.some(
              (issue) => issue.rule === rule && issue.column === column.name,
            )
          : false,
      )
      .map((column) => column.id);
  const tokens: Record<string, string> = {};
  for (const column of semantic?.content.columns ?? []) {
    const known = columns.find((c) => c.id === column.id);
    if (
      known?.type === "string" &&
      column.review.state === "confirmed" &&
      column.null_policy.mode === "explicit_tokens" &&
      column.null_policy.tokens?.length
    )
      tokens[column.id] = column.null_policy.tokens.join(", ");
  }
  return {
    tokens,
    trim: ids("Q-003"),
    cast: {},
    drop: ids("Q-001"),
    dedupe: {
      enabled: diagnostic.quality.issues.some(
        (issue) => issue.rule === "Q-002",
      ),
      column_ids: columns.map((column) => column.id),
      null_keys: "group_nulls",
    },
  };
}

/** Orden fijo: marcadores → recortar → convertir → excluir nulos → deduplicar. */
export function draftSteps(draft: Draft, columns: Column[]): PlanStep[] {
  const steps: PlanStep[] = [];
  const next = (): PlanStep["input"] =>
    steps.length
      ? { kind: "step", step_id: steps[steps.length - 1].id }
      : { kind: "input", alias: "source" };
  const ordered = columns.map((column) => column.id);
  const groups = new Map<string, string[]>();
  for (const id of ordered) {
    const tokens = splitTokens(draft.tokens[id] ?? "");
    if (!tokens.length) continue;
    const key = JSON.stringify(tokens);
    groups.set(key, [...(groups.get(key) ?? []), id]);
  }
  [...groups.entries()].forEach(([key, ids], index) =>
    steps.push({
      id: `null_tokens_${index + 1}`,
      operation: "cleaning.normalize_null_tokens",
      version: 1,
      input: next(),
      parameters: { column_ids: ids, tokens: JSON.parse(key) as string[] },
    }),
  );
  if (draft.trim.length)
    steps.push({
      id: "trim",
      operation: "cleaning.trim_whitespace",
      version: 1,
      input: next(),
      parameters: { column_ids: draft.trim },
    });
  ordered
    .filter((id) => draft.cast[id])
    .forEach((id, index) => {
      const conversion = draft.cast[id];
      steps.push({
        id: `cast_${index + 1}`,
        operation: "cleaning.cast",
        version: 1,
        input: next(),
        parameters: {
          column_id: id,
          type: conversion.type,
          format: FORMATS[conversion.type],
          scale: conversion.type === "decimal" ? conversion.scale : null,
          confirm_identifier_conversion: conversion.confirm,
        },
      });
    });
  if (draft.drop.length)
    steps.push({
      id: "drop_nulls",
      operation: "cleaning.filter_rows",
      version: 1,
      input: next(),
      parameters: {
        column_ids: draft.drop,
        predicate: "is_null",
        match: "any",
      },
    });
  if (draft.dedupe.enabled && draft.dedupe.column_ids.length)
    steps.push({
      id: "dedupe",
      operation: "cleaning.deduplicate",
      version: 1,
      input: next(),
      parameters: {
        column_ids: draft.dedupe.column_ids,
        keep: "first",
        null_keys: draft.dedupe.null_keys,
      },
    });
  return steps;
}

export function CleaningStage({
  projectId,
  version,
  diagnostic,
  archived,
  onShowDerived,
  onDirtyChange,
  copilotPlanId = null,
  onDismissCopilotPlan,
}: {
  projectId: string;
  version: DatasetVersion;
  diagnostic: Diagnostic;
  archived: boolean;
  onShowDerived: (parentVersionId: string) => void;
  onDirtyChange: (dirty: boolean) => void;
  /** Plan guardado desde el copiloto (Fase 10): mismo ciclo de vista previa y aprobación. */
  copilotPlanId?: string | null;
  onDismissCopilotPlan?: () => void;
}) {
  const tables = useRepresentations(version.id);
  const table = tables.data?.[0];
  const understanding = useUnderstanding(table?.id ?? "");
  if (tables.isPending || (table && understanding.isPending))
    return (
      <p className="empty-copy" role="status">
        Cargando la tabla publicada…
      </p>
    );
  if (!table?.columns)
    return (
      <p className="empty-copy">
        No hay una tabla publicada con esquema para proponer una limpieza.
      </p>
    );
  // Sin contexto semántico (error de lectura) la propuesta sigue siendo técnica.
  const head = understanding.data?.head ?? null;
  const suggestions = new Map(
    (understanding.data?.suggestions ?? []).map((s) => [
      s.column_id,
      s.suggested_type ?? undefined,
    ]),
  );
  const columns: Column[] = table.columns.map((column) => {
    const id = String(column.id);
    const semantic = head?.content.columns.find((c) => c.id === id);
    return {
      id,
      name: String(column.name),
      type: (column.technical_type as DataType | undefined) ?? "string",
      suggested:
        diagnostic.profile.columns.find((c) => c.name === column.name)
          ?.suggested_type ?? suggestions.get(id),
      identifier:
        semantic?.role === "identifier" &&
        semantic.review.state === "confirmed",
    };
  });
  return (
    <Proposal
      key={`${table.id}-${head?.id ?? "none"}`}
      projectId={projectId}
      table={{ id: table.id, sha256: table.sha256 }}
      columns={columns}
      diagnostic={diagnostic}
      semantic={head}
      archived={archived}
      onShowDerived={onShowDerived}
      onDirtyChange={onDirtyChange}
      copilotPlanId={copilotPlanId}
      onDismissCopilotPlan={onDismissCopilotPlan}
    />
  );
}

function Proposal({
  projectId,
  table,
  columns,
  diagnostic,
  semantic,
  archived,
  onShowDerived,
  onDirtyChange,
  copilotPlanId,
  onDismissCopilotPlan,
}: {
  projectId: string;
  table: { id: string; sha256: string };
  columns: Column[];
  diagnostic: Diagnostic;
  semantic: Semantic | null;
  archived: boolean;
  onShowDerived: (parentVersionId: string) => void;
  onDirtyChange: (dirty: boolean) => void;
  copilotPlanId: string | null;
  onDismissCopilotPlan?: () => void;
}) {
  const suggested = useMemo(
    () => initialDraft(diagnostic, columns, semantic),
    [diagnostic, columns, semantic],
  );
  const [draft, setDraft] = useState<Draft>(suggested);
  const [planId, setPlanId] = useState<string | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const router = useRouter();
  // El borrador sólo existe en memoria hasta guardarse como plan: si difiere de la sugerencia
  // del diagnóstico, salir de la etapa lo perdería y se recalcularía desde el diagnóstico.
  const dirty = !planId && JSON.stringify(draft) !== JSON.stringify(suggested);
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  const [route, setRoute] = useUnsavedGuard(dirty);
  const createPlan = useCreatePlan(projectId);
  const createPreview = useCreatePreview();
  const steps = draftSteps(draft, columns);
  const pending = createPlan.isPending || createPreview.isPending;
  const semanticRef: SemanticRef | null = semantic
    ? {
        id: semantic.id,
        revision: semantic.revision,
        content_sha256: semantic.content_sha256,
      }
    : null;
  const key = semantic?.content.key;
  const declaredKey =
    key?.review.state === "confirmed" && key.column_ids.length ? key : null;
  const unconfirmed = columns.filter(
    (column) =>
      column.identifier &&
      draft.cast[column.id] &&
      ["integer", "decimal"].includes(draft.cast[column.id].type) &&
      !draft.cast[column.id].confirm,
  );
  const duplicates = diagnostic.quality.issues.find(
    (issue) => issue.rule === "Q-002",
  )?.affected_rows;
  const count = (rule: string, name: string) =>
    diagnostic.quality.issues.find(
      (issue) => issue.rule === rule && issue.column === name,
    )?.affected_rows;
  function toggle(kind: "trim" | "drop", id: string, on: boolean) {
    setDraft({
      ...draft,
      [kind]: on
        ? columns
            .filter((c) => c.id === id || draft[kind].includes(c.id))
            .map((c) => c.id)
        : draft[kind].filter((item) => item !== id),
    });
  }
  function convert(id: string, conversion: Conversion | null) {
    const cast = { ...draft.cast };
    if (conversion) cast[id] = conversion;
    else delete cast[id];
    setDraft({ ...draft, cast });
  }
  function dedupeColumn(id: string, on: boolean) {
    setDraft({
      ...draft,
      dedupe: {
        ...draft.dedupe,
        column_ids: on
          ? columns
              .filter(
                (c) => c.id === id || draft.dedupe.column_ids.includes(c.id),
              )
              .map((c) => c.id)
          : draft.dedupe.column_ids.filter((item) => item !== id),
      },
    });
  }
  async function preview(revision: string) {
    const run = await createPreview.mutateAsync(revision);
    setPreviewId(run.id);
  }
  if (previewId && planId)
    return (
      <section className="cleaning-stage" aria-label="Limpieza supervisada">
        <div className="section-heading">
          <div>
            <h3>Vista previa del efecto</h3>
            <p>Calculada con el mismo motor que la aplicación final.</p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setPreviewId(null);
              setPlanId(null);
            }}
          >
            <Pencil size={14} /> Editar propuesta
          </Button>
        </div>
        <EffectPreview
          key={previewId}
          executionId={previewId}
          projectId={projectId}
          archived={archived}
          onRepeat={() => void preview(planId).catch(() => {})}
          onShowDerived={onShowDerived}
        />
        {createPreview.isError && (
          <p className="auth-error" role="alert">
            {errorMessage(createPreview.error)}
          </p>
        )}
      </section>
    );
  if (copilotPlanId && !previewId)
    return (
      <section className="cleaning-stage" aria-label="Limpieza supervisada">
        <div className="section-heading">
          <div>
            <h3>Plan de limpieza propuesto por el copiloto</h3>
            <p>
              Está guardado como plan y no ha cambiado ningún dato. Genera la
              vista previa sobre todo el dataset y aprueba el efecto exacto
              antes de aplicarlo.
            </p>
          </div>
          {onDismissCopilotPlan && (
            <Button variant="outline" size="sm" onClick={onDismissCopilotPlan}>
              Usar la propuesta del diagnóstico
            </Button>
          )}
        </div>
        <Button
          disabled={archived || pending}
          onClick={() => {
            setPlanId(copilotPlanId);
            void preview(copilotPlanId).catch(() => {});
          }}
        >
          Generar vista previa
        </Button>
        {createPreview.isError && (
          <p className="auth-error" role="alert">
            {errorMessage(createPreview.error)}
          </p>
        )}
      </section>
    );
  const locked = archived || pending;
  return (
    <section className="cleaning-stage" aria-label="Limpieza supervisada">
      <div className="section-heading">
        <div>
          <p className="eyebrow">PROPUESTA · BORRADOR EDITABLE</p>
          <h3>Propuesta de limpieza</h3>
          <p>
            Sugerida a partir del diagnóstico. Nada cambia hasta que apruebes el
            efecto exacto; el original y esta versión se conservan.
          </p>
        </div>
        {dirty && <span className="badge review">Cambios sin guardar</span>}
      </div>
      <p className="fine-print muted" data-testid="semantic-pin">
        {semantic
          ? `Usa la revisión semántica ${semantic.revision} de esta tabla (marcadores de nulo e identificadores confirmados).`
          : "Sin revisión semántica: la propuesta es sólo técnica."}
      </p>
      <div className="table-scroll bordered">
        <table aria-label="Propuesta por columna">
          <thead>
            <tr>
              <th>Columna</th>
              <th>Marcadores de nulo</th>
              <th>Recortar espacios (bordes)</th>
              <th>Convertir a</th>
              <th>Excluir registros con nulo</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((column) => {
              const text = column.type === "string";
              const spaces = count("Q-003", column.name);
              const nulls = count("Q-001", column.name);
              const conversion = draft.cast[column.id];
              return (
                <tr key={column.id}>
                  <td>
                    <strong>{column.name}</strong>
                    <br />
                    <span className="badge neutral">
                      {TYPE_LABELS[column.type]}
                    </span>
                  </td>
                  <td>
                    <input
                      aria-label={`Marcadores de nulo de ${column.name}`}
                      placeholder={text ? "p. ej. NA, -" : "Sólo texto"}
                      disabled={locked || !text}
                      value={draft.tokens[column.id] ?? ""}
                      onChange={(e) => {
                        const tokens = { ...draft.tokens };
                        if (e.target.value) tokens[column.id] = e.target.value;
                        else delete tokens[column.id];
                        setDraft({ ...draft, tokens });
                      }}
                    />
                  </td>
                  <td>
                    <label className="check-option">
                      <input
                        type="checkbox"
                        aria-label={`Recortar ${column.name}`}
                        disabled={locked || !text}
                        checked={draft.trim.includes(column.id)}
                        onChange={(e) =>
                          toggle("trim", column.id, e.target.checked)
                        }
                      />
                      {spaces ? (
                        <span className="badge review">
                          Q-003 · {spaces} celda(s)
                        </span>
                      ) : null}
                    </label>
                  </td>
                  <td>
                    {text ? (
                      <div className="cast-options">
                        <select
                          aria-label={`Convertir ${column.name}`}
                          disabled={locked}
                          value={conversion?.type ?? ""}
                          onChange={(e) =>
                            convert(
                              column.id,
                              e.target.value
                                ? {
                                    type: e.target.value as CastType,
                                    scale: conversion?.scale ?? 2,
                                    confirm: false,
                                  }
                                : null,
                            )
                          }
                        >
                          <option value="">Sin convertir</option>
                          {(Object.keys(FORMATS) as CastType[]).map((type) => (
                            <option key={type} value={type}>
                              {TYPE_LABELS[type]}
                            </option>
                          ))}
                        </select>
                        {conversion?.type === "decimal" && (
                          <label>
                            Escala
                            <input
                              className="scale-input"
                              type="number"
                              min={0}
                              max={12}
                              aria-label={`Escala de ${column.name}`}
                              disabled={locked}
                              value={conversion.scale}
                              onChange={(e) =>
                                convert(column.id, {
                                  ...conversion,
                                  scale: Math.min(
                                    12,
                                    Math.max(0, Number(e.target.value) || 0),
                                  ),
                                })
                              }
                            />
                          </label>
                        )}
                        {column.suggested &&
                          column.suggested !== "string" &&
                          !conversion && (
                            <small className="muted">
                              Sugerido: {TYPE_LABELS[column.suggested]}
                            </small>
                          )}
                        {column.identifier &&
                          conversion &&
                          ["integer", "decimal"].includes(conversion.type) && (
                            <label className="check-option identifier-guard">
                              <input
                                type="checkbox"
                                aria-label={`Confirmo convertir el identificador ${column.name} a número`}
                                disabled={locked}
                                checked={conversion.confirm}
                                onChange={(e) =>
                                  convert(column.id, {
                                    ...conversion,
                                    confirm: e.target.checked,
                                  })
                                }
                              />
                              <span>
                                Es un identificador confirmado: convertirlo a
                                número puede perder códigos. Confirmo la
                                conversión.
                              </span>
                            </label>
                          )}
                      </div>
                    ) : (
                      <span className="muted">
                        Ya es {TYPE_LABELS[column.type].toLowerCase()}
                      </span>
                    )}
                  </td>
                  <td>
                    <label className="check-option">
                      <input
                        type="checkbox"
                        aria-label={`Excluir nulos de ${column.name}`}
                        disabled={locked}
                        checked={draft.drop.includes(column.id)}
                        onChange={(e) =>
                          toggle("drop", column.id, e.target.checked)
                        }
                      />
                      {nulls ? (
                        <span className="badge review">
                          Q-001 · {nulls} registro(s)
                        </span>
                      ) : null}
                    </label>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <fieldset className="dedupe-options" disabled={locked}>
        <legend>
          <label className="check-option">
            <input
              type="checkbox"
              aria-label="Eliminar registros duplicados"
              checked={draft.dedupe.enabled}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  dedupe: { ...draft.dedupe, enabled: e.target.checked },
                })
              }
            />
            Eliminar registros duplicados (se conserva la primera aparición)
            {duplicates ? (
              <span className="badge review">
                Q-002 · {duplicates} registro(s)
              </span>
            ) : null}
          </label>
        </legend>
        {draft.dedupe.enabled && (
          <>
            <div className="chip-options" aria-label="Columnas de la clave">
              {columns.map((column) => (
                <label key={column.id} className="check-option">
                  <input
                    type="checkbox"
                    aria-label={`Clave de deduplicación: ${column.name}`}
                    checked={draft.dedupe.column_ids.includes(column.id)}
                    onChange={(e) => dedupeColumn(column.id, e.target.checked)}
                  />
                  {column.name}
                </label>
              ))}
            </div>
            <label>
              Claves con nulos{" "}
              <select
                aria-label="Claves con nulos"
                value={draft.dedupe.null_keys}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    dedupe: {
                      ...draft.dedupe,
                      null_keys: e.target.value as NullKeys,
                    },
                  })
                }
              >
                <option value="group_nulls">
                  Agrupar: los nulos se consideran iguales
                </option>
                <option value="reject">
                  Rechazar: si hay nulos en la clave, la limpieza falla
                </option>
              </select>
            </label>
            {declaredKey && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  setDraft({
                    ...draft,
                    dedupe: {
                      enabled: true,
                      column_ids: declaredKey.column_ids,
                      null_keys: declaredKey.null_policy,
                    },
                  })
                }
              >
                Usar la clave declarada en la revisión semántica
              </Button>
            )}
          </>
        )}
      </fieldset>
      <div className="info-banner">
        <ShieldCheck size={18} />
        <span>
          Se aplica en este orden: marcadores de nulo, recortar, convertir,
          excluir y deduplicar. Convertir no recorta espacios ni acepta formatos
          regionales: si un solo valor no convierte, no se publica nada y la
          vista previa lista los valores y el motivo.
        </span>
      </div>
      {unconfirmed.length > 0 && (
        <p className="auth-error" role="alert">
          Confirma la conversión de {unconfirmed.map((c) => c.name).join(", ")}:
          la revisión semántica la marca como identificador.
        </p>
      )}
      {(createPlan.isError || createPreview.isError) && (
        <p className="auth-error" role="alert">
          {errorMessage(createPlan.error ?? createPreview.error)}
        </p>
      )}
      <div className="form-footer">
        <span className="fine-print muted">
          {steps.length
            ? `Se guardará como plan de ${steps.length} paso(s) sobre la tabla ${table.id.slice(0, 8)}.`
            : "Selecciona al menos una operación."}
        </span>
        <Button
          disabled={locked || !steps.length || unconfirmed.length > 0}
          onClick={async () => {
            try {
              const plan = await createPlan.mutateAsync({
                table_artifact_id: table.id,
                table_sha256: table.sha256,
                semantic_ref: semanticRef,
                steps,
              });
              setPlanId(plan.id);
              await preview(plan.id);
            } catch {
              /* Error visible; la propuesta se conserva. */
            }
          }}
        >
          {pending ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <Eye size={16} />
          )}
          Generar vista previa
        </Button>
      </div>
      {route && (
        <Dialog title="Hay cambios sin guardar" onClose={() => setRoute(null)}>
          <p className="dialog-copy">
            Puedes seguir editando o descartar esta propuesta para salir. Los
            datos, los planes guardados y las versiones se conservan.
          </p>
          <div className="form-footer">
            <Button variant="ghost" onClick={() => setRoute(null)}>
              Seguir editando
            </Button>
            <Button
              onClick={() => {
                onDirtyChange(false);
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
