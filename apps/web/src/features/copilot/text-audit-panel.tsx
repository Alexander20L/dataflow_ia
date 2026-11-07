"use client";
import { useState } from "react";
import { ClipboardCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { Provenance } from "@/features/analytics/results";
import {
  UNAVAILABLE,
  useCopilotStatus,
  useRequestTextAudit,
  useTextAudits,
  type Segment,
} from "./api";

const SEVERITY: Record<string, string> = {
  alta: "Alta",
  media: "Media",
  baja: "Baja",
};

/**
 * Auditoría textual IA de la revisión publicada que se está viendo (Fase 11F). Sólo explica
 * resultados ya calculados: no cambia el dashboard y, si la IA falla, el dashboard sigue igual.
 */
export function TextAuditPanel({
  projectId,
  revisionId,
}: {
  projectId: string;
  revisionId: string;
}) {
  const status = useCopilotStatus(projectId);
  const audits = useTextAudits(revisionId);
  const request = useRequestTextAudit(projectId, revisionId);
  const [evidence, setEvidence] = useState<{ run: string; id: string } | null>(
    null,
  );
  const audit = request.data?.audit ?? audits.data?.[0] ?? null;
  const available = status.data?.available ?? false;
  const reason = status.data?.reason;
  const content = audit?.content;
  const omitted = audit?.cards.filter((c) => !c.included) ?? [];

  // Una función de render (no un componente anidado): cada cifra abre su procedencia.
  function render(segments: Segment[]) {
    return (
      <>
        {segments.map((segment, i) =>
          segment.kind === "evidence" &&
          segment.evidence_id &&
          segment.execution_id ? (
            <button
              key={i}
              className="text-link copilot-figure"
              aria-label={`De dónde sale ${segment.text}`}
              onClick={() =>
                setEvidence({
                  run: segment.execution_id!,
                  id: segment.evidence_id!,
                })
              }
            >
              {segment.text}
            </button>
          ) : segment.kind === "unverified" ? (
            <mark
              key={i}
              className="copilot-unverified"
              title="El modelo escribió una cifra que no sale de un resultado calculado: se retiró."
            >
              {segment.text}
            </mark>
          ) : (
            <span key={i}>{segment.text}</span>
          ),
        )}
      </>
    );
  }

  return (
    <section className="text-audit" aria-label="Auditoría textual">
      <div className="section-heading">
        <h4>
          <ClipboardCheck size={16} /> Auditoría textual (IA)
        </h4>
        <Button
          size="sm"
          variant="outline"
          disabled={!available || request.isPending}
          onClick={() => request.mutate()}
        >
          {request.isPending
            ? "Auditando…"
            : audit
              ? "Volver a pedir"
              : "Auditar este dashboard"}
        </Button>
      </div>
      {!available && reason && (
        <p className="muted">{UNAVAILABLE[reason] ?? reason}</p>
      )}
      {request.isError && (
        <p className="auth-error" role="alert">
          {errorMessage(request.error)} El dashboard no cambia.
        </p>
      )}
      {request.data?.reused && (
        <p className="copilot-note">
          Auditoría guardada para estos mismos resultados: no se volvió a llamar
          al modelo.
        </p>
      )}
      {audit && content && (
        <div className="text-audit-body">
          <p>{render(content.resumen_ejecutivo)}</p>
          {content.alertas_criticas.length > 0 && (
            <>
              <h5>Alertas</h5>
              <ul>
                {content.alertas_criticas.map((alert, i) => (
                  <li key={i}>
                    <span className="badge neutral">
                      {SEVERITY[alert.severidad] ?? alert.severidad}
                    </span>{" "}
                    <strong>{render(alert.titulo)}</strong>
                    {" · "}
                    {render(alert.detalle)}
                  </li>
                ))}
              </ul>
            </>
          )}
          <h5>Recomendaciones</h5>
          <ol>
            {content.recomendaciones.map((recommendation, i) => (
              <li key={i}>{render(recommendation)}</li>
            ))}
          </ol>
          {content.unverified_numbers > 0 && (
            <p className="copilot-note">
              Se retiraron {content.unverified_numbers}{" "}
              {content.unverified_numbers === 1
                ? "cifra escrita"
                : "cifras escritas"}{" "}
              por el modelo sin evidencia.
            </p>
          )}
          {omitted.length > 0 && (
            <p className="copilot-note">
              Sin auditar (no tienen un resultado terminado):{" "}
              {omitted.map((c) => c.title).join(", ")}.
            </p>
          )}
          <p className="copilot-note">
            {audit.provider} · {audit.model} · {audit.prompt_id}@
            {audit.prompt_version}. Cada cifra es un enlace a «De dónde sale
            este número».
          </p>
        </div>
      )}
      {evidence && (
        <Provenance
          runId={evidence.run}
          evidenceId={evidence.id}
          onClose={() => setEvidence(null)}
        />
      )}
    </section>
  );
}
