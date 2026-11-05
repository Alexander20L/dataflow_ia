"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, LoaderCircle, Pencil, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import { useUnsavedGuard } from "@/lib/use-unsaved-guard";
import { useRepresentations } from "@/features/executions/api";
import type { DatasetVersion, Diagnostic } from "@/features/ingestion/api";
import { useCreatePlan, type PlanStep } from "@/features/planning/api";
import { EffectPreview } from "./effect-preview";
import { useCreatePreview } from "./api";

type Column = { id: string; name: string };
type Draft = { trim: string[]; drop: string[] };

/** Borrador inicial desde el diagnóstico: Q-003 → recortar; Q-001 → excluir nulos. */
export function initialDraft(diagnostic: Diagnostic, columns: Column[]): Draft {
  const ids = (rule: string) =>
    columns
      .filter((column) =>
        diagnostic.quality.issues.some(
          (issue) => issue.rule === rule && issue.column === column.name,
        ),
      )
      .map((column) => column.id);
  return { trim: ids("Q-003"), drop: ids("Q-001") };
}

export function draftSteps(draft: Draft): PlanStep[] {
  const steps: PlanStep[] = [];
  if (draft.trim.length)
    steps.push({
      id: "trim",
      operation: "cleaning.trim_whitespace",
      version: 1,
      input: { kind: "input", alias: "source" },
      parameters: { column_ids: draft.trim },
    });
  if (draft.drop.length)
    steps.push({
      id: "drop_nulls",
      operation: "cleaning.filter_rows",
      version: 1,
      input: steps.length
        ? { kind: "step", step_id: "trim" }
        : { kind: "input", alias: "source" },
      parameters: {
        column_ids: draft.drop,
        predicate: "is_null",
        match: "any",
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
}: {
  projectId: string;
  version: DatasetVersion;
  diagnostic: Diagnostic;
  archived: boolean;
  onShowDerived: (parentVersionId: string) => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const tables = useRepresentations(version.id);
  const table = tables.data?.[0];
  if (tables.isPending)
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
  return (
    <Proposal
      key={table.id}
      projectId={projectId}
      table={{ id: table.id, sha256: table.sha256 }}
      columns={table.columns.map((column) => ({
        id: String(column.id),
        name: String(column.name),
      }))}
      diagnostic={diagnostic}
      archived={archived}
      onShowDerived={onShowDerived}
      onDirtyChange={onDirtyChange}
    />
  );
}

function Proposal({
  projectId,
  table,
  columns,
  diagnostic,
  archived,
  onShowDerived,
  onDirtyChange,
}: {
  projectId: string;
  table: { id: string; sha256: string };
  columns: Column[];
  diagnostic: Diagnostic;
  archived: boolean;
  onShowDerived: (parentVersionId: string) => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const suggested = useMemo(
    () => initialDraft(diagnostic, columns),
    [diagnostic, columns],
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
  const steps = draftSteps(draft);
  const pending = createPlan.isPending || createPreview.isPending;
  const count = (rule: string, name: string) =>
    diagnostic.quality.issues.find(
      (issue) => issue.rule === rule && issue.column === name,
    )?.affected_rows;
  function toggle(kind: keyof Draft, id: string, on: boolean) {
    setDraft({
      ...draft,
      [kind]: on
        ? columns
            .filter((c) => c.id === id || draft[kind].includes(c.id))
            .map((c) => c.id)
        : draft[kind].filter((item) => item !== id),
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
      <div className="table-scroll bordered">
        <table aria-label="Propuesta por columna">
          <thead>
            <tr>
              <th>Columna</th>
              <th>Recortar espacios (bordes)</th>
              <th>Excluir registros con nulo</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((column) => {
              const spaces = count("Q-003", column.name);
              const nulls = count("Q-001", column.name);
              return (
                <tr key={column.id}>
                  <td>
                    <strong>{column.name}</strong>
                  </td>
                  <td>
                    <label className="check-option">
                      <input
                        type="checkbox"
                        aria-label={`Recortar ${column.name}`}
                        disabled={archived || pending}
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
                    <label className="check-option">
                      <input
                        type="checkbox"
                        aria-label={`Excluir nulos de ${column.name}`}
                        disabled={archived || pending}
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
      <div className="info-banner">
        <ShieldCheck size={18} />
        <span>
          Recortar quita espacios, tabuladores y saltos de línea de los bordes;
          una celda que queda vacía pasa a ser nula. Excluir conserva el orden
          del resto de registros. Se recorta antes de excluir.
        </span>
      </div>
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
          disabled={archived || pending || !steps.length}
          onClick={async () => {
            try {
              const plan = await createPlan.mutateAsync({
                table_artifact_id: table.id,
                table_sha256: table.sha256,
                semantic_ref: null,
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
