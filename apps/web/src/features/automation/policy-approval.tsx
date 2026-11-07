"use client";
import { Bot, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { useApprovalOrigin, useApproveByPolicy } from "./api";

/** Evalúa la vista previa con la política del proyecto (Fase 11B). Si la autoriza, se crea la
 * aprobación del efecto exacto; si no, se muestran los motivos y nada cambia. */
export function PolicyApproveButton({
  executionId,
  disabled,
}: {
  executionId: string;
  disabled: boolean;
}) {
  const approve = useApproveByPolicy(executionId);
  const decision = approve.data;
  return (
    <>
      <Button
        variant="outline"
        disabled={disabled || approve.isPending}
        onClick={() => void approve.mutateAsync().catch(() => {})}
      >
        {approve.isPending ? (
          <LoaderCircle size={16} className="spin" />
        ) : (
          <Bot size={16} />
        )}
        Aprobar con la política
      </Button>
      {approve.isError && (
        <p className="auth-error" role="alert">
          {errorMessage(approve.error)}
        </p>
      )}
      {decision?.evaluation.decision === "blocked" && (
        <div
          className="warning-banner policy-reasons"
          role="alert"
          aria-label="Revisión necesaria"
        >
          <strong>
            Revisión necesaria: la política no autoriza este efecto.
          </strong>
          <ul>
            {decision.evaluation.reasons.map((reason, index) => (
              <li key={`${reason.code}-${index}`}>
                {reason.message}
                {reason.column ? ` Columna «${reason.column}».` : ""}
                {reason.measured
                  ? ` Medido: ${reason.measured}; límite: ${reason.limit}.`
                  : ""}{" "}
                <code>{reason.code}</code>
              </li>
            ))}
          </ul>
          <span className="fine-print">
            Puedes revisarlo y aprobarlo tú con «Aprobar efecto…».
          </span>
        </div>
      )}
    </>
  );
}

/** «Aprobada automáticamente por la política rev N» cuando corresponde. */
export function ApprovalOriginNote({ approvalId }: { approvalId: string }) {
  const origin = useApprovalOrigin(approvalId);
  if (!origin.data?.automatic) return null;
  return (
    <span className="badge calculated" data-testid="approval-origin">
      <Bot size={12} /> Aprobada automáticamente por la política rev{" "}
      {origin.data.policy_revision}
    </span>
  );
}
