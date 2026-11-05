"use client";
import { AlertTriangle, CheckCircle2, ShieldCheck } from "lucide-react";
import { problemLabels, type Plan, type Problem } from "./api";

export function PlanSummary({
  plan,
  dirty,
  onGoToStep,
  onOpenUnderstanding,
}: {
  plan: Plan;
  dirty: boolean;
  onGoToStep: (stepId: string | null) => void;
  onOpenUnderstanding: () => void;
}) {
  const { validation } = plan;
  return (
    <section className="plan-summary" aria-label="Resumen del plan">
      <div className="plan-summary-heading">
        <h4>
          Revisión {plan.revision}
          {plan.head_revision !== plan.revision && ` de ${plan.head_revision}`}
        </h4>
        <span
          className={`badge ${validation.valid ? "completed" : "review"}`}
          data-testid="plan-status"
        >
          {validation.valid
            ? "Válido · listo para ejecutar"
            : `Incompleto · ${validation.problems.length} pendiente(s)`}
        </span>
      </div>
      <dl className="plan-facts">
        <div>
          <dt>Tabla de entrada fijada</dt>
          <dd className="mono" title={plan.input.artifact_id}>
            {plan.input.artifact_id}
          </dd>
          <dd className="mono" data-testid="plan-input-sha">
            SHA-256 {plan.input.artifact_sha256}
          </dd>
          <dd className="fine-print muted">
            Versión {plan.input.version_id.slice(0, 8)} · no cambia aunque
            cambie la versión predeterminada del proyecto.
          </dd>
        </div>
        <div>
          <dt>Revisión semántica fijada</dt>
          {plan.semantic_ref ? (
            <dd className="mono">
              Revisión {plan.semantic_ref.revision} · SHA{" "}
              {plan.semantic_ref.content_sha256.slice(0, 16)}
            </dd>
          ) : (
            <dd className="muted">Ninguna · análisis técnico</dd>
          )}
        </div>
        <div>
          <dt>Contenido</dt>
          <dd className="mono" title={plan.content_sha256}>
            SHA-256 {plan.content_sha256.slice(0, 16)} · catálogo{" "}
            {validation.catalog_version}
          </dd>
        </div>
      </dl>
      {dirty && (
        <p className="fine-print muted" role="status">
          La validación corresponde a la revisión guardada. Guarda los cambios
          para volver a validar.
        </p>
      )}
      {validation.valid ? (
        <p className="plan-valid">
          <CheckCircle2 size={16} /> Sin requisitos pendientes.
        </p>
      ) : (
        <ul className="plan-problems" aria-label="Problemas pendientes">
          {validation.problems.map((problem, index) => (
            <li key={`${problem.code}-${problem.step_id}-${index}`}>
              <AlertTriangle size={15} />
              <div>
                <strong>{problemLabels[problem.code]}</strong>
                <span>{problem.message}</span>
                <small className="mono">{problem.code}</small>
              </div>
              <ProblemLink
                problem={problem}
                onGoToStep={onGoToStep}
                onOpenUnderstanding={onOpenUnderstanding}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ProblemLink({
  problem,
  onGoToStep,
  onOpenUnderstanding,
}: {
  problem: Problem;
  onGoToStep: (stepId: string | null) => void;
  onOpenUnderstanding: () => void;
}) {
  if (problem.resolve_in === "understanding")
    return (
      <button
        type="button"
        className="link-button"
        onClick={onOpenUnderstanding}
      >
        <ShieldCheck size={14} /> Resolver en Entendimiento
      </button>
    );
  return (
    <button
      type="button"
      className="link-button"
      onClick={() => onGoToStep(problem.step_id ?? null)}
    >
      {problem.step_id
        ? `Ir al paso «${problem.step_id}»`
        : "Ir al catálogo de operaciones"}
    </button>
  );
}
