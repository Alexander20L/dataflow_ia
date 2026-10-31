"use client";
import { useState } from "react";
import { Activity, ArrowRight, GitBranch, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import { useApp } from "@/lib/providers";
import { useSemanticHistory } from "@/features/understanding/api";
import {
  useCancelExecution,
  useCreateAnalysis,
  useExecution,
  useExecutionQuality,
  useRepresentations,
  useVersionExecutions,
  type AnalysisKind,
} from "./api";

const labels = {
  queued: "En cola",
  running: "En ejecución",
  succeeded: "Completada",
  failed: "Error",
  cancelled: "Cancelada",
};
export function ExecutionPanel({
  versionId,
  archived,
}: {
  versionId: string;
  archived: boolean;
}) {
  const runs = useVersionExecutions(versionId);
  const tables = useRepresentations(versionId);
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [kind, setKind] = useState<AnalysisKind>("profile_quality");
  const [semanticId, setSemanticId] = useState<string | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const create = useCreateAnalysis(versionId);
  const cancel = useCancelExecution(versionId);
  const { notify } = useApp();
  const run = runs.data?.find((run) => run.id === selected) ?? runs.data?.[0];
  const table =
    tables.data?.find((table) => table.id === selectedTable) ??
    tables.data?.[0];
  const detail = useExecution(run);
  const quality = useExecutionQuality(run);
  const semantics = useSemanticHistory(table?.id);
  const semanticRef =
    semantics.data?.items.find((item) => item.id === semanticId) ?? null;
  return (
    <section
      className="execution-panel"
      aria-label="Ejecuciones independientes"
    >
      <div className="section-heading">
        <div>
          <h3>
            <Activity size={17} /> Ejecuciones independientes
          </h3>
          <p>
            Cada análisis conserva su plan, intentos y resultados. No sustituye
            el diagnóstico inicial de la carga.
          </p>
        </div>
        <span className="badge neutral">Planes de sistema</span>
      </div>
      <div className="analysis-controls">
        <div>
          <label htmlFor="analysis-table">Tabla de entrada fijada</label>
          <select
            id="analysis-table"
            value={table?.id ?? ""}
            disabled={tables.isPending || create.isPending}
            onChange={(e) => {
              setSelectedTable(e.target.value);
              setSemanticId(null);
            }}
          >
            {tables.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id.slice(0, 8)} · SHA {item.sha256.slice(0, 10)}
              </option>
            ))}
            {!tables.data?.length && (
              <option value="">Sin tabla publicada</option>
            )}
          </select>
        </div>
        <div>
          <label htmlFor="analysis-kind">Análisis</label>
          <select
            id="analysis-kind"
            value={kind}
            onChange={(e) => setKind(e.target.value as AnalysisKind)}
            disabled={create.isPending}
          >
            <option value="profile_quality">Perfil y calidad</option>
            <option value="quality_only">Sólo calidad</option>
          </select>
        </div>
        <div>
          <label htmlFor="analysis-semantics">
            Contexto semántico (opcional)
          </label>
          <select
            id="analysis-semantics"
            value={semanticId ?? ""}
            disabled={create.isPending || semantics.isPending}
            onChange={(e) => setSemanticId(e.target.value || null)}
          >
            <option value="">Sin contrato · análisis técnico</option>
            {semantics.data?.items.map((item) => (
              <option key={item.id} value={item.id}>
                Revisión {item.revision} · {item.content_sha256.slice(0, 10)}
              </option>
            ))}
          </select>
        </div>
        <Button
          disabled={
            !table ||
            archived ||
            create.isPending ||
            (!!semanticId && !semanticRef)
          }
          onClick={async () => {
            if (!table) return;
            try {
              const result = await create.mutateAsync({
                table_artifact_id: table.id,
                table_sha256: table.sha256,
                analysis_kind: kind,
                semantic_ref: semanticRef,
              });
              setSelected(result.id);
              notify("Análisis encolado sobre la tabla seleccionada.");
            } catch {
              /* Error visible. */
            }
          }}
        >
          {create.isPending ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <ArrowRight size={16} />
          )}
          Ejecutar análisis
        </Button>
      </div>
      {semantics.isError && (
        <p className="auth-error" role="alert">
          {errorMessage(semantics.error)}
        </p>
      )}
      {(semantics.data?.total ?? 0) > 20 && (
        <p className="fine-print muted">
          El selector muestra las últimas 20 revisiones; el historial semántico
          permite consultar las anteriores.
        </p>
      )}
      {tables.isError && (
        <p className="auth-error" role="alert">
          {errorMessage(tables.error)}
        </p>
      )}
      {create.isError && (
        <p className="auth-error" role="alert">
          {errorMessage(create.error)}
        </p>
      )}
      {runs.isPending ? (
        <p className="empty-copy" role="status">
          Cargando ejecuciones…
        </p>
      ) : runs.isError ? (
        <div className="empty-state compact">
          <p role="alert">{errorMessage(runs.error)}</p>
          <Button onClick={() => void runs.refetch()}>Reintentar</Button>
        </div>
      ) : (
        <>
          <div className="dataset-controls">
            <label htmlFor="selected-execution">
              <GitBranch size={14} />
              Ejecución
            </label>
            <select
              id="selected-execution"
              value={run?.id ?? ""}
              onChange={(e) => setSelected(e.target.value)}
            >
              {runs.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.kind === "csv_import"
                    ? "Ingesta baseline"
                    : item.plan?.content.steps &&
                        Array.isArray(item.plan.content.steps) &&
                        item.plan.content.steps.length === 1
                      ? "Sólo calidad"
                      : "Perfil y calidad"}{" "}
                  · {item.id.slice(0, 8)} · {labels[item.state]}
                </option>
              ))}
            </select>
            {run && (
              <span
                className={`badge ${run.state === "succeeded" ? "completed" : "neutral"}`}
              >
                {labels[run.state]}
              </span>
            )}
            {run && ["queued", "running"].includes(run.state) && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirmCancel(true)}
              >
                Cancelar análisis
              </Button>
            )}
          </div>
          <p className="fine-print muted">
            Últimas 50 ejecuciones de esta versión.
          </p>
          {run && (
            <div className="run-inspection">
              <div className="original-meta">
                <span className="mono">ID {run.id}</span>
                <span>{run.attempts} intento(s)</span>
                <span>
                  {run.reproducibility === "complete"
                    ? "Configuración registrada"
                    : "Historia 0.3 · configuración parcial"}
                </span>
              </div>
              {run.error_message && (
                <p className="auth-error" role="alert">
                  {run.error_code}: {run.error_message}
                </p>
              )}
              {detail.isError && (
                <p className="auth-error" role="alert">
                  {errorMessage(detail.error)}
                </p>
              )}
              {detail.data?.plan && (
                <details className="plan-details">
                  <summary>Ver plan y configuración fijados</summary>
                  <p className="mono">
                    SHA-256 {detail.data.plan.content_sha256}
                  </p>
                  <pre>{JSON.stringify(detail.data.plan.content, null, 2)}</pre>
                </details>
              )}
              {detail.data && (
                <div className="attempt-history">
                  <h4>Historial de intentos</h4>
                  {detail.data.attempt_history.length ? (
                    detail.data.attempt_history.map((attempt) => (
                      <div className="attempt-row" key={attempt.id}>
                        <strong>
                          #{attempt.number} · {attempt.state}
                        </strong>
                        <span>
                          Python {String(attempt.environment.python_version)} ·
                          Polars {String(attempt.environment.polars_version)}
                        </span>
                        <small
                          className="mono"
                          title={attempt.environment_sha256}
                        >
                          Entorno {attempt.environment_sha256.slice(0, 16)}
                        </small>
                      </div>
                    ))
                  ) : (
                    <p className="muted fine-print">
                      {run.reproducibility === "legacy_partial"
                        ? "No existían snapshots individuales. Se conserva el contador histórico sin inventar intentos."
                        : "El worker aún no ha iniciado un intento."}
                    </p>
                  )}
                </div>
              )}
              {quality.isError && (
                <p className="auth-error" role="alert">
                  {errorMessage(quality.error)}
                </p>
              )}
              {quality.data && (
                <div className="execution-quality">
                  <h4>Calidad de esta ejecución</h4>
                  <div className="mini-metrics">
                    <div>
                      <small>Celdas vacías</small>
                      <strong>{quality.data.missing_cells}</strong>
                    </div>
                    <div>
                      <small>Duplicados adicionales</small>
                      <strong>{quality.data.duplicate_rows}</strong>
                    </div>
                    <div>
                      <small>Completitud</small>
                      <strong>
                        {quality.data.completeness_percent.toLocaleString(
                          "es-ES",
                        )}{" "}
                        %
                      </strong>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
      {confirmCancel && run && (
        <Dialog
          title="¿Cancelar esta ejecución?"
          onClose={() => setConfirmCancel(false)}
        >
          <p className="dialog-copy">
            Se cancelará únicamente el trabajo seleccionado. El archivo original
            y los resultados de otras ejecuciones se conservan.
          </p>
          {cancel.isError && (
            <p className="auth-error" role="alert">
              {errorMessage(cancel.error)}
            </p>
          )}
          <div className="form-footer">
            <Button variant="ghost" onClick={() => setConfirmCancel(false)}>
              Volver
            </Button>
            <Button
              disabled={cancel.isPending}
              onClick={async () => {
                try {
                  await cancel.mutateAsync(run.id);
                  setConfirmCancel(false);
                } catch {
                  /* Error visible. */
                }
              }}
            >
              Confirmar cancelación
            </Button>
          </div>
        </Dialog>
      )}
    </section>
  );
}
