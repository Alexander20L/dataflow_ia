"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Bot, Send, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { Provenance } from "@/features/analytics/results";
import {
  UNAVAILABLE,
  useConversation,
  useConversations,
  useCopilotStatus,
  useCreateConversation,
  useExplain,
  useSendMessage,
  type Message,
} from "./api";
import { ProposalCard } from "./proposal-card";

/** Etapas del workspace a las que una propuesta puede llevar. */
export type CopilotTarget = "understanding" | "analysis";

export function CopilotPanel({
  projectId,
  versionId,
  versionNumber,
  archived,
  onOpenStage,
  onOpenCleaningPlan,
}: {
  projectId: string;
  versionId: string;
  versionNumber: number;
  archived: boolean;
  onOpenStage: (target: CopilotTarget) => void;
  onOpenCleaningPlan: (planRevisionId: string) => void;
}) {
  const status = useCopilotStatus(projectId);
  const conversations = useConversations(projectId);
  const [chosen, setChosen] = useState<string | null>(null);
  const conversationId = chosen ?? conversations.data?.[0]?.id ?? null;
  const conversation = useConversation(conversationId);
  const create = useCreateConversation(projectId);
  const send = useSendMessage(projectId);
  const explain = useExplain(projectId);
  const [text, setText] = useState("");
  const [evidence, setEvidence] = useState<{
    run: string;
    id: string;
  } | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const messages = conversation.data?.messages ?? [];
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest" });
  }, [messages.length]);

  const available = status.data?.available ?? false;
  const busy = send.isPending || explain.isPending || create.isPending;

  async function ensureConversation() {
    if (conversationId) return conversationId;
    const created = await create.mutateAsync("Conversación");
    setChosen(created.id);
    return created.id;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    try {
      const id = await ensureConversation();
      await send.mutateAsync({ conversationId: id, versionId, text: value });
      setText("");
    } catch {
      /* Error visible bajo el formulario. */
    }
  }

  async function explainRun(executionId: string) {
    try {
      const id = await ensureConversation();
      await explain.mutateAsync({ conversationId: id, executionId });
    } catch {
      /* Error visible bajo el formulario. */
    }
  }

  const error = send.error ?? explain.error ?? create.error;
  return (
    <section className="copilot-panel" aria-label="Copiloto de análisis">
      <div className="section-heading">
        <div>
          <h3>
            <Sparkles size={16} /> Copiloto de análisis
          </h3>
          <p>
            Propone consultas, métricas y limpiezas del catálogo sobre v
            {versionNumber}. Nada se ejecuta sin tu confirmación y las cifras
            salen siempre de resultados calculados.
          </p>
        </div>
        <span className="badge ai">IA · propuestas</span>
      </div>
      {status.isPending ? (
        <p className="empty-copy" role="status">
          Comprobando el copiloto…
        </p>
      ) : status.isError ? (
        <p className="auth-error" role="alert">
          {errorMessage(status.error)}
        </p>
      ) : !available ? (
        <div className="copilot-unavailable" role="status">
          <Bot size={18} />
          <div>
            <strong>Copiloto no disponible</strong>
            <p>{UNAVAILABLE[status.data.reason ?? "disabled"]}</p>
          </div>
        </div>
      ) : null}
      {messages.length > 0 && (
        <ol
          className="copilot-messages"
          aria-label="Conversación con el copiloto"
        >
          {messages.map((message) => (
            <li
              key={message.id}
              className={`copilot-message ${message.role === "user" ? "from-user" : "from-copilot"}`}
            >
              <small>{message.role === "user" ? "Tú" : "Copiloto · IA"}</small>
              {message.role === "user" ? (
                <p>{message.text}</p>
              ) : (
                <AssistantMessage
                  message={message}
                  projectId={projectId}
                  archived={archived}
                  explaining={explain.isPending}
                  onEvidence={(run, id) => setEvidence({ run, id })}
                  onExplain={(run) => void explainRun(run)}
                  onOpenStage={onOpenStage}
                  onOpenCleaningPlan={onOpenCleaningPlan}
                />
              )}
            </li>
          ))}
        </ol>
      )}
      <div ref={end} />
      {available && !archived && (
        <form className="copilot-form" onSubmit={(e) => void submit(e)}>
          <label htmlFor="copilot-question" className="sr-only">
            Pregunta al copiloto
          </label>
          <textarea
            id="copilot-question"
            rows={2}
            maxLength={2000}
            placeholder="Por ejemplo: «Compara las ventas mensuales por región»"
            value={text}
            disabled={busy}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void submit(e);
              }
            }}
          />
          <Button type="submit" disabled={busy || !text.trim()}>
            <Send size={15} />
            {send.isPending ? "Pensando…" : "Enviar"}
          </Button>
        </form>
      )}
      {explain.isPending && (
        <p className="empty-copy" role="status">
          El copiloto está redactando la explicación…
        </p>
      )}
      {error && (
        <p className="auth-error" role="alert">
          {errorMessage(error)}
        </p>
      )}
      <p className="copilot-disclaimer">
        Al copiloto sólo se envían nombres, tipos y roles de columnas, métricas,
        conteos agregados y resultados calculados; nunca filas ni valores de
        ejemplo.
      </p>
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

function AssistantMessage({
  message,
  projectId,
  archived,
  explaining,
  onEvidence,
  onExplain,
  onOpenStage,
  onOpenCleaningPlan,
}: {
  message: Message;
  projectId: string;
  archived: boolean;
  explaining: boolean;
  onEvidence: (run: string, evidenceId: string) => void;
  onExplain: (run: string) => void;
  onOpenStage: (target: CopilotTarget) => void;
  onOpenCleaningPlan: (planRevisionId: string) => void;
}) {
  const content = message.assistant;
  if (!content) return null;
  return (
    <>
      <p className={content.status === "ok" ? undefined : "copilot-error"}>
        {content.segments.map((segment, i) =>
          segment.kind === "evidence" &&
          segment.evidence_id &&
          segment.execution_id ? (
            <button
              key={i}
              className="text-link copilot-figure"
              aria-label={`De dónde sale ${segment.text}`}
              onClick={() =>
                onEvidence(segment.execution_id!, segment.evidence_id!)
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
      </p>
      {content.unverified_numbers > 0 && (
        <p className="copilot-note">
          Se retiraron {content.unverified_numbers}{" "}
          {content.unverified_numbers === 1
            ? "cifra escrita"
            : "cifras escritas"}{" "}
          por el modelo sin evidencia.
        </p>
      )}
      <ProposalCard
        message={message}
        projectId={projectId}
        archived={archived}
        explaining={explaining}
        onExplain={onExplain}
        onOpenStage={onOpenStage}
        onOpenCleaningPlan={onOpenCleaningPlan}
      />
    </>
  );
}
