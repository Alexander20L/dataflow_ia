"use client";
import {
  BarChart3,
  Brush,
  CircleHelp,
  FileQuestion,
  Play,
  Sigma,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { useAnalysisRun } from "@/features/analytics/api";
import {
  aggregationLabel,
  comparisonLabel,
  GRAINS,
} from "@/features/analytics/labels";
import {
  OPERATION_LABELS,
  useProposalAction,
  type ActionKind,
  type ActionLink,
  type Message,
  type ProposalProblem,
} from "./api";
import type { CopilotTarget } from "./copilot-panel";

const TOPICS: Record<string, string> = {
  metric: "Falta definir una métrica",
  measure: "Falta confirmar la medida",
  currency: "Falta confirmar la moneda",
  business_date: "Falta confirmar la fecha de negocio",
  dimension: "La agrupación pedida es ambigua",
  other: "Necesito más contexto",
};

export function ProposalCard({
  message,
  projectId,
  archived,
  explaining,
  onExplain,
  onOpenStage,
  onOpenCleaningPlan,
}: {
  message: Message;
  projectId: string;
  archived: boolean;
  explaining: boolean;
  onExplain: (run: string) => void;
  onOpenStage: (target: CopilotTarget) => void;
  onOpenCleaningPlan: (planRevisionId: string) => void;
}) {
  const content = message.assistant!;
  const action = useProposalAction(projectId);
  const link = (kind: ActionLink["kind"]) =>
    message.links.find((l) => l.kind === kind);
  async function run(kind: ActionKind) {
    try {
      return await action.mutateAsync({ messageId: message.id, action: kind });
    } catch {
      return null; /* Error visible en la tarjeta. */
    }
  }
  const failure = action.isError && (
    <p className="auth-error" role="alert">
      {errorMessage(action.error)}
    </p>
  );

  if (content.clarification) {
    const target = content.clarification.resolve_in;
    return (
      <div
        className="copilot-card"
        role="group"
        aria-label="Pregunta del copiloto"
      >
        <h4>
          <CircleHelp size={15} /> {TOPICS[content.clarification.topic]}
        </h4>
        {target === "understanding" && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onOpenStage("understanding")}
          >
            Ir a Entendimiento
          </Button>
        )}
        {target === "metrics" && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onOpenStage("analysis")}
          >
            Ir a Análisis
          </Button>
        )}
      </div>
    );
  }

  if (content.metric) {
    const card = content.metric;
    const draft = card.draft as {
      label: string;
      aggregation: string;
      filters: unknown[];
    };
    const created = link("metric");
    return (
      <div className="copilot-card" role="group" aria-label="Métrica propuesta">
        <h4>
          <Sigma size={15} /> Métrica propuesta
          <Validity valid={card.valid} />
        </h4>
        <dl className="definition-list">
          <dt>Nombre</dt>
          <dd>{draft.label}</dd>
          <dt>Cálculo</dt>
          <dd>
            {aggregationLabel(draft.aggregation)} de{" "}
            {card.measure_column ?? "una columna desconocida"}
          </dd>
          <dt>Fecha de negocio</dt>
          <dd>{card.time_column ?? "Sin fecha"}</dd>
          <dt>Filtros</dt>
          <dd>{draft.filters.length || "Ninguno"}</dd>
        </dl>
        <Problems problems={card.problems} onOpenStage={onOpenStage} />
        {created ? (
          <p className="copilot-done" role="status">
            Métrica creada. Ya puedes pedir la consulta.
          </p>
        ) : (
          <Button
            size="sm"
            disabled={!card.valid || archived || action.isPending}
            onClick={() => void run("create-metric")}
          >
            Crear métrica
          </Button>
        )}
        {failure}
      </div>
    );
  }

  if (content.cleaning) {
    const card = content.cleaning;
    const saved = link("cleaning_plan");
    return (
      <div
        className="copilot-card"
        role="group"
        aria-label="Plan de limpieza propuesto"
      >
        <h4>
          <Brush size={15} /> Plan de limpieza propuesto
          <Validity valid={card.valid} />
        </h4>
        <ol className="copilot-steps">
          {card.steps.map((step, i) => (
            <li key={i}>
              {OPERATION_LABELS[String(step.operation)] ??
                String(step.operation)}
            </li>
          ))}
        </ol>
        <p className="copilot-note">
          Abrirlo lo guarda como plan; no cambia datos. En Limpieza verás la
          vista previa y aprobarás el efecto exacto antes de aplicarlo.
        </p>
        <Problems problems={card.problems} onOpenStage={onOpenStage} />
        <Button
          size="sm"
          disabled={!card.valid || archived || action.isPending}
          onClick={async () => {
            const plan =
              saved?.plan_revision_id ??
              (await run("cleaning-plan"))?.link.plan_revision_id;
            if (plan) onOpenCleaningPlan(plan);
          }}
        >
          Abrir plan de limpieza
        </Button>
        {failure}
      </div>
    );
  }

  if (content.query) {
    const card = content.query;
    const executed = link("query_execution");
    const grain = GRAINS.find((g) => g.value === card.time_grain)?.label;
    const range = card.time_range as {
      start: string | null;
      end: string | null;
    } | null;
    const ranking = card.ranking as {
      direction: string;
      top_n: number;
    } | null;
    return (
      <div
        className="copilot-card"
        role="group"
        aria-label="Consulta propuesta"
      >
        <h4>
          <BarChart3 size={15} /> Consulta propuesta
          <Validity valid={card.valid} />
        </h4>
        <dl className="definition-list">
          <dt>Métricas</dt>
          <dd>{card.metrics.map((m) => m.name).join(", ") || "Ninguna"}</dd>
          <dt>Agrupar por</dt>
          <dd>
            {[
              ...card.dimensions.map((d) => d.name),
              ...(grain ? [grain] : []),
            ].join(" · ") || "Sin agrupación"}
          </dd>
          {range && (
            <>
              <dt>Periodo</dt>
              <dd>
                {range.start ?? "inicio"} – {range.end ?? "fin"}
              </dd>
            </>
          )}
          {card.comparisons.length > 0 && (
            <>
              <dt>Comparar con</dt>
              <dd>{card.comparisons.map(comparisonLabel).join(", ")}</dd>
            </>
          )}
          {ranking && (
            <>
              <dt>Ranking</dt>
              <dd>
                {ranking.direction === "desc" ? "Mayores" : "Menores"}{" "}
                {ranking.top_n}
              </dd>
            </>
          )}
          {card.share_of_total.length > 0 && (
            <>
              <dt>% del total</dt>
              <dd>{card.share_of_total.map((m) => m.name).join(", ")}</dd>
            </>
          )}
        </dl>
        <Problems problems={card.problems} onOpenStage={onOpenStage} />
        {executed?.execution_id ? (
          <ExecutionState
            executionId={executed.execution_id}
            explaining={explaining}
            archived={archived}
            onExplain={onExplain}
          />
        ) : (
          <Button
            size="sm"
            disabled={!card.valid || archived || action.isPending}
            onClick={() => void run("run-query")}
          >
            <Play size={14} /> Ejecutar consulta
          </Button>
        )}
        {failure}
      </div>
    );
  }
  return null;
}

function Validity({ valid }: { valid: boolean }) {
  return (
    <span className={`badge ${valid ? "completed" : "review"}`}>
      {valid ? "Validada con el catálogo" : "No válida"}
    </span>
  );
}

function Problems({
  problems,
  onOpenStage,
}: {
  problems: ProposalProblem[];
  onOpenStage: (target: CopilotTarget) => void;
}) {
  if (!problems.length) return null;
  return (
    <ul className="copilot-problems" aria-label="Problemas de la propuesta">
      {problems.map((problem, i) => (
        <li key={i}>
          <FileQuestion size={13} /> {problem.message}{" "}
          {problem.resolve_in === "understanding" && (
            <button
              className="text-link"
              onClick={() => onOpenStage("understanding")}
            >
              Ir a Entendimiento
            </button>
          )}
          {problem.resolve_in === "metrics" && (
            <button
              className="text-link"
              onClick={() => onOpenStage("analysis")}
            >
              Ir a Análisis
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

function ExecutionState({
  executionId,
  explaining,
  archived,
  onExplain,
}: {
  executionId: string;
  explaining: boolean;
  archived: boolean;
  onExplain: (run: string) => void;
}) {
  const run = useAnalysisRun(executionId);
  const state = run.data?.state;
  if (state === "succeeded")
    return (
      <div className="copilot-actions">
        <span className="badge calculated" role="status">
          Consulta calculada
        </span>
        <Button
          size="sm"
          variant="outline"
          disabled={explaining || archived}
          onClick={() => onExplain(executionId)}
        >
          Explicar resultado
        </Button>
      </div>
    );
  if (state === "failed" || state === "cancelled")
    return (
      <p className="auth-error" role="alert">
        La consulta no terminó: {run.data?.error_message ?? state}
      </p>
    );
  return (
    <p className="empty-copy" role="status">
      Calculando la consulta…
    </p>
  );
}
