"use client";
import { useState } from "react";
import { Activity, GitBranch } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api";
import { PlanEditor } from "@/features/planning/plan-editor";
import {
  useCancelExecution,
  useExecution,
  useExecutionQuality,
  useVersionExecutions,
  type Execution,
} from "./api";
import { RulesReport } from "@/features/quality/report";
import { runHasStep, useQualityRulesReport } from "@/features/quality/api";
import { useAnalysisResult } from "@/features/analytics/api";
import { Results } from "@/features/analytics/results";

const labels = {
  queued: "En cola",
  running: "En ejecución",
  succeeded: "Completada",
  failed: "Error",
  cancelled: "Cancelada",
};
function runLabel(run: Execution) {
  if (run.kind === "csv_import") return "Ingesta baseline";
  if (run.kind === "plan") return `Plan revisión ${run.plan?.revision ?? "?"}`;
  if (run.kind === "cleaning_preview") return "Vista previa de limpieza";
  if (run.kind === "cleaning_apply") return "Aplicación de limpieza";
  if (run.kind === "report_render") return "Informe a PDF";
  if (run.kind === "overview_audit") return "Explicación automática IA";
  const steps = run.plan?.content.steps;
  return Array.isArray(steps) && steps.length === 1
    ? "Sólo calidad (0.5)"
    : "Perfil y calidad (0.5)";
}
export function ExecutionPanel({
  projectId,
  versionId,
  archived,
  onDirtyChange,
  onOpenUnderstanding,
}: {
  projectId: string;
  versionId: string;
  archived: boolean;
  onDirtyChange: (dirty: boolean) => void;
  onOpenUnderstanding: () => void;
}) {
  const runs = useVersionExecutions(versionId);
  const [selected, setSelected] = useState<string | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const cancel = useCancelExecution(versionId);
  const run = runs.data?.find((run) => run.id === selected) ?? runs.data?.[0];
  const detail = useExecution(run);
  // Sólo se consulta el resultado que el plan produce: csv-quality-v1 o reglas v2.
  const quality = useExecutionQuality(
    run,
    run?.kind !== "overview_audit" &&
      (run?.kind !== "plan" || runHasStep(run, "quality.evaluate@1")),
  );
  const rules = useQualityRulesReport(
    run,
    runHasStep(run, "quality.evaluate@2"),
  );
  // Resultados de análisis (analytics.query@1, @2 o @3) también en el historial (Fase 8).
  const analysis = useAnalysisResult(
    run?.id ?? null,
    run?.state === "succeeded" &&
      (runHasStep(run, "analytics.query@1") ||
        runHasStep(run, "analytics.query@2") ||
        runHasStep(run, "analytics.query@3")),
  );
  return (
    <section
      className="execution-panel"
      aria-label="Ejecuciones independientes"
    >
      <div className="section-heading">
        <div>
          <h3>
            <Activity size={17} /> Planes y ejecuciones
          </h3>
          <p>
            Arma un plan con operaciones del catálogo, guárdalo como revisión
            inmutable y ejecútalo sobre su tabla exacta. Cada ejecución conserva
            su plan, intentos y resultados; no sustituye el diagnóstico inicial
            de la carga.
          </p>
        </div>
        <span className="badge neutral">Catálogo analysis-v8</span>
      </div>
      <PlanEditor
        projectId={projectId}
        versionId={versionId}
        archived={archived}
        onDirtyChange={onDirtyChange}
        onOpenUnderstanding={onOpenUnderstanding}
        onExecuted={setSelected}
      />
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
                  {runLabel(item)} · {item.id.slice(0, 8)} ·{" "}
                  {labels[item.state]}
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
              {rules.data && <RulesReport report={rules.data} />}
              {analysis.isError && (
                <p className="auth-error" role="alert">
                  {errorMessage(analysis.error)}
                </p>
              )}
              {run && analysis.data && (
                <div
                  className="execution-analysis"
                  aria-label="Resultado del análisis de esta ejecución"
                >
                  <h4>Resultado del análisis</h4>
                  <Results result={analysis.data} runId={run.id} />
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
