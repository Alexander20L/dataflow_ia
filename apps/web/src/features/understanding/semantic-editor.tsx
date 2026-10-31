"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { History, Save, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import { useApp } from "@/lib/providers";
import { useRepresentations } from "@/features/executions/api";
import { ColumnDetails } from "./column-details";
import { RevisionHistory } from "./revision-history";
import {
  normalizeDraft,
  revisionDraft,
  roles,
  reviews,
  types,
  useSaveSemantics,
  useUnderstanding,
  type EditorDraft,
  type SemanticContext,
  type ReviewState,
} from "./api";

type Props = {
  versionId: string;
  baselineExecutionId: string;
  archived: boolean;
  onDirtyChange: (dirty: boolean) => void;
};
export function SemanticUnderstanding({
  versionId,
  baselineExecutionId,
  archived,
  onDirtyChange,
}: Props) {
  const tables = useRepresentations(versionId);
  const table = tables.data?.find(
    (table) => table.execution_id === baselineExecutionId,
  );
  if (tables.isPending)
    return (
      <p role="status" className="empty-copy">
        Cargando la representación semántica…
      </p>
    );
  if (tables.isError)
    return (
      <div className="empty-state">
        <p role="alert">{errorMessage(tables.error)}</p>
        <Button onClick={() => void tables.refetch()}>Reintentar</Button>
      </div>
    );
  if (!table)
    return (
      <p className="empty-copy">
        No hay una representación baseline publicada para revisar.
      </p>
    );
  return (
    <SemanticContextView
      key={table.id}
      artifactId={table.id}
      archived={archived}
      onDirtyChange={onDirtyChange}
    />
  );
}

function SemanticContextView({
  artifactId,
  archived,
  onDirtyChange,
}: {
  artifactId: string;
  archived: boolean;
  onDirtyChange: Props["onDirtyChange"];
}) {
  const query = useUnderstanding(artifactId);
  if (query.isPending)
    return (
      <p className="empty-copy" role="status">
        Cargando contexto y sugerencias…
      </p>
    );
  if (query.isError)
    return (
      <div className="empty-state">
        <p role="alert">{errorMessage(query.error)}</p>
        <Button onClick={() => void query.refetch()}>Reintentar</Button>
      </div>
    );
  return (
    <SemanticForm
      artifactId={artifactId}
      context={query.data}
      archived={archived}
      onDirtyChange={onDirtyChange}
    />
  );
}

function SemanticForm({
  artifactId,
  context,
  archived,
  onDirtyChange,
}: {
  artifactId: string;
  context: SemanticContext;
  archived: boolean;
  onDirtyChange: Props["onDirtyChange"];
}) {
  const [draft, setDraft] = useState(() => normalizeDraft(context.editable));
  const [baseline, setBaseline] = useState(() =>
    JSON.stringify(normalizeDraft(context.editable)),
  );
  const [expected, setExpected] = useState(context.head?.revision ?? 0);
  const [saved, setSaved] = useState(context.head);
  const [history, setHistory] = useState(false);
  const [details, setDetails] = useState<string | null>(null);
  const [reset, setReset] = useState(false);
  const [route, setRoute] = useState<string | null>(null);
  const router = useRouter();
  const save = useSaveSemantics(artifactId);
  const { notify } = useApp();
  const dirty = JSON.stringify(draft) !== baseline;
  const newer = (context.head?.revision ?? 0) !== expected;
  const facts = context.columns;

  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  useEffect(() => {
    if (!dirty) return;
    const unload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const click = (event: MouseEvent) => {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey ||
        event.altKey
      )
        return;
      const anchor =
        event.target instanceof Element ? event.target.closest("a") : null;
      if (
        !(anchor instanceof HTMLAnchorElement) ||
        anchor.target === "_blank" ||
        anchor.hasAttribute("download")
      )
        return;
      const url = new URL(anchor.href, window.location.href);
      if (
        url.origin !== window.location.origin ||
        url.pathname.startsWith("/api/") ||
        url.pathname + url.search ===
          window.location.pathname + window.location.search
      )
        return;
      event.preventDefault();
      event.stopPropagation();
      setRoute(url.pathname + url.search + url.hash);
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", click, true);
    return () => {
      window.removeEventListener("beforeunload", unload);
      document.removeEventListener("click", click, true);
    };
  }, [dirty]);

  function update(value: EditorDraft) {
    setDraft(value);
    onDirtyChange(JSON.stringify(value) !== baseline);
  }
  function columnUpdate(
    id: string,
    changes: Partial<EditorDraft["columns"][number]>,
    decision = false,
  ) {
    update({
      ...draft,
      columns: draft.columns.map((c) =>
        c.column_id === id
          ? {
              ...c,
              ...changes,
              ...(!decision ? { review_state: "pending" as const } : {}),
            }
          : c,
      ),
    });
  }
  function loadCurrent() {
    const value = normalizeDraft(context.editable);
    setDraft(value);
    setBaseline(JSON.stringify(value));
    setExpected(context.head?.revision ?? 0);
    setSaved(context.head);
    onDirtyChange(false);
    setReset(false);
    save.reset();
  }
  const selectedColumn = draft.columns.find((c) => c.column_id === details);
  return (
    <section className="semantic-editor" aria-label="Revisión semántica">
      <div className="section-heading">
        <div>
          <p className="eyebrow">CONTEXTO DECLARADO · SIN TRANSFORMACIONES</p>
          <h3>Revisión semántica de tus datos</h3>
          <p>
            Define qué representan las filas y columnas. Puedes guardar
            información parcial.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setHistory(true)}>
          <History size={15} />
          Historial semántico
        </Button>
      </div>
      <div className="semantic-status">
        <span className="badge neutral">
          {saved
            ? `Revisión ${saved.revision} guardada`
            : "Sin revisión guardada"}
        </span>
        {dirty && <span className="badge review">Cambios sin guardar</span>}
        <small className="mono">
          Tabla {artifactId.slice(0, 8)} · SHA{" "}
          {context.table_ref.artifact_sha256.slice(0, 16)}
        </small>
      </div>
      {newer && (
        <div className="warning-banner" role="status">
          <span>
            El servidor tiene la revisión {context.head?.revision ?? 0}; estás
            editando la {expected}. No se sobrescribirán cambios.
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => (dirty ? setReset(true) : loadCurrent())}
          >
            Cargar revisión actual
          </Button>
        </div>
      )}
      {archived && (
        <div className="info-banner">
          <span>
            Proyecto archivado: puedes consultar revisiones, pero no guardar
            cambios.
          </span>
        </div>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            const result = await save.mutateAsync({
              table_sha256: context.table_ref.artifact_sha256,
              expected_revision: expected,
              draft,
            });
            const value = revisionDraft(result.revision);
            setDraft(value);
            setBaseline(JSON.stringify(value));
            setExpected(result.revision.revision);
            setSaved(result.revision);
            onDirtyChange(false);
            notify(
              result.changed
                ? `Revisión semántica ${result.revision.revision} guardada. Datos originales intactos.`
                : `Revisión ${result.revision.revision} recuperada sin duplicar cambios.`,
            );
          } catch {
            /* Error visible y borrador conservado. */
          }
        }}
      >
        <fieldset disabled={archived || save.isPending}>
          <div className="semantic-overview">
            <div>
              <label htmlFor="semantic-dataset-description">
                Descripción del dataset
              </label>
              <textarea
                id="semantic-dataset-description"
                rows={3}
                maxLength={2000}
                value={draft.dataset_description ?? ""}
                placeholder="Contenido y contexto del archivo"
                onChange={(e) =>
                  update({
                    ...draft,
                    dataset_description: e.target.value || null,
                  })
                }
              />
            </div>
            <div>
              <label htmlFor="semantic-row-grain">
                ¿Qué representa cada fila?
              </label>
              <textarea
                id="semantic-row-grain"
                rows={3}
                maxLength={500}
                value={draft.row_grain.description ?? ""}
                placeholder="Ej. una línea de pedido, un cliente, una medición…"
                onChange={(e) =>
                  update({
                    ...draft,
                    row_grain: {
                      description: e.target.value || null,
                      review_state: "pending",
                    },
                  })
                }
              />
              <label className="sr-only" htmlFor="semantic-grain-review">
                Revisión del significado de cada fila
              </label>
              <select
                id="semantic-grain-review"
                value={draft.row_grain.review_state}
                onChange={(e) =>
                  update({
                    ...draft,
                    row_grain: {
                      ...draft.row_grain,
                      review_state: e.target.value as ReviewState,
                    },
                  })
                }
              >
                {Object.entries(reviews).map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="section-heading">
            <h3>Roles e interpretación de columnas</h3>
            <span className="badge neutral">
              {
                draft.columns.filter((c) => c.review_state === "confirmed")
                  .length
              }
              /{draft.columns.length} confirmadas
            </span>
          </div>
          <div className="table-scroll bordered semantic-columns">
            <table>
              <thead>
                <tr>
                  <th>Columna / procedencia</th>
                  <th>Rol declarado</th>
                  <th>Tipo de interpretación</th>
                  <th>Revisión</th>
                  <th>Detalles</th>
                </tr>
              </thead>
              <tbody>
                {draft.columns.map((column, index) => {
                  const fact = facts[index];
                  const hint = context.suggestions.find(
                    (s) => s.column_id === column.column_id,
                  );
                  const previous = saved?.content.columns[index];
                  return (
                    <tr key={column.column_id}>
                      <td>
                        <strong>{fact.name}</strong>
                        <small className="cell-subtitle">
                          Columna {index + 1} · {column.column_id.slice(0, 8)}
                        </small>
                        <small className="cell-subtitle">
                          Físico: {fact.technical_type} · propuesta:{" "}
                          {hint?.suggested_type ?? "pendiente"}
                        </small>
                        <small
                          className="cell-subtitle"
                          title={hint?.reasons.join(" ")}
                        >
                          Regla: {hint?.rule_version}
                        </small>
                        {previous && (
                          <small className="cell-subtitle">
                            Guardado:{" "}
                            {previous.review.origin === "user"
                              ? "usuario"
                              : previous.review.origin}{" "}
                            · {reviews[previous.review.state]}
                          </small>
                        )}
                      </td>
                      <td>
                        <select
                          aria-label={`Rol de ${fact.name}`}
                          value={column.role}
                          onChange={(e) => {
                            const role = e.target.value as typeof column.role;
                            columnUpdate(column.column_id, {
                              role,
                              ...(role !== "measure"
                                ? { unit: null, currency: null }
                                : {}),
                            });
                          }}
                        >
                          {Object.entries(roles).map(([key, label]) => (
                            <option key={key} value={key}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <select
                          aria-label={`Interpretación de ${fact.name}`}
                          value={column.interpretation_type ?? ""}
                          onChange={(e) => {
                            const type = e.target.value as NonNullable<
                              typeof column.interpretation_type
                            >;
                            const formats = {
                              integer: "integer_ascii",
                              decimal: "decimal_dot",
                              date: "iso_date",
                              boolean: "boolean_lowercase",
                            } as const;
                            columnUpdate(column.column_id, {
                              interpretation_type: type || null,
                              parse_format:
                                type && type !== "string"
                                  ? formats[type]
                                  : null,
                            });
                          }}
                        >
                          <option value="">Sin definir</option>
                          {Object.entries(types).map(([key, label]) => (
                            <option key={key} value={key}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <select
                          aria-label={`Revisión de ${fact.name}`}
                          value={column.review_state}
                          onChange={(e) =>
                            columnUpdate(
                              column.column_id,
                              { review_state: e.target.value as ReviewState },
                              true,
                            )
                          }
                        >
                          {Object.entries(reviews).map(([key, label]) => (
                            <option key={key} value={key}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="text-link"
                          aria-label={`Detalles de ${fact.name}`}
                          onClick={() => setDetails(column.column_id)}
                        >
                          Editar detalles
                        </button>
                        <small className="cell-subtitle">
                          {column.currency ?? column.unit ?? "Unidad pendiente"}
                        </small>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <section className="semantic-key">
            <h3>Clave del registro</h3>
            <p>
              Declarar una clave no garantiza que los valores sean únicos y no
              elimina duplicados.
            </p>
            <div className="key-column-list">
              {facts.map((fact) => (
                <label key={fact.id}>
                  <input
                    type="checkbox"
                    aria-label={`Clave: ${fact.name}`}
                    checked={draft.key.column_ids.includes(fact.id)}
                    onChange={(e) =>
                      update({
                        ...draft,
                        key: {
                          ...draft.key,
                          review_state: "pending",
                          column_ids: e.target.checked
                            ? [...draft.key.column_ids, fact.id]
                            : draft.key.column_ids.filter(
                                (id) => id !== fact.id,
                              ),
                        },
                      })
                    }
                  />
                  {fact.name}
                </label>
              ))}
            </div>
            <div className="semantic-key-controls">
              <div>
                <label htmlFor="semantic-key-nulls">Nulos en la clave</label>
                <select
                  id="semantic-key-nulls"
                  value={draft.key.null_policy}
                  onChange={(e) =>
                    update({
                      ...draft,
                      key: {
                        ...draft.key,
                        null_policy: e.target
                          .value as typeof draft.key.null_policy,
                        review_state: "pending",
                      },
                    })
                  }
                >
                  <option value="reject">No admitidos</option>
                  <option value="group_nulls">Comparar nulos como grupo</option>
                </select>
              </div>
              <div>
                <label htmlFor="semantic-key-review">
                  Revisión de la clave
                </label>
                <select
                  id="semantic-key-review"
                  value={draft.key.review_state}
                  onChange={(e) =>
                    update({
                      ...draft,
                      key: {
                        ...draft.key,
                        review_state: e.target.value as ReviewState,
                      },
                    })
                  }
                >
                  {Object.entries(reviews).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </section>
        </fieldset>
        <div className="info-banner">
          <ShieldCheck size={18} />
          <span>
            Guardar declara significado y formato. No convierte tipos, no aplica
            políticas de nulos y no modifica la calidad ni los bytes de los
            datos. Las propuestas rechazadas no se consideran confirmadas.
          </span>
        </div>
        {context.warnings.length > 0 && (
          <div className="semantic-observations">
            <h4>
              Observaciones{" "}
              {context.head
                ? `de la revisión ${context.head.revision}`
                : "iniciales"}
            </h4>
            {context.warnings.map((warning, index) => (
              <p key={`${warning.code}-${index}`}>{warning.message}</p>
            ))}
            {dirty && (
              <small>
                Las observaciones de tu borrador se actualizarán al guardar.
              </small>
            )}
          </div>
        )}
        {save.isError && (
          <p className="auth-error" role="alert">
            {errorMessage(save.error)}
          </p>
        )}
        <div className="form-footer">
          <span className="fine-print muted">
            {saved
              ? `Guardada ${new Date(saved.created_at).toLocaleString("es-ES")}`
              : "Las sugerencias aún no son decisiones confirmadas."}
          </span>
          <Button type="submit" disabled={archived || save.isPending || newer}>
            <Save size={16} />
            {save.isPending ? "Guardando…" : "Guardar revisión semántica"}
          </Button>
        </div>
      </form>
      {selectedColumn && (
        <ColumnDetails
          key={selectedColumn.column_id}
          name={facts.find((f) => f.id === details)?.name ?? "columna"}
          column={selectedColumn}
          onClose={() => setDetails(null)}
          onApply={(value) => {
            columnUpdate(value.column_id, value);
            setDetails(null);
          }}
        />
      )}
      {history && (
        <RevisionHistory
          artifactId={artifactId}
          head={context.head}
          onClose={() => setHistory(false)}
        />
      )}
      {reset && (
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
            <Button onClick={loadCurrent}>Descartar y cargar</Button>
          </div>
        </Dialog>
      )}
      {route && (
        <Dialog title="Hay cambios sin guardar" onClose={() => setRoute(null)}>
          <p className="dialog-copy">
            Puedes seguir editando o descartar este borrador para salir. Los
            datos y las revisiones guardadas se conservan.
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
