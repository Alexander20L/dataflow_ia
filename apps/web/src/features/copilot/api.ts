import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

type Schemas = components["schemas"];
export type CopilotStatus = Schemas["CopilotStatus"];
export type Conversation = Schemas["Conversation"];
export type Message = Schemas["Message"];
export type AssistantContent = Schemas["AssistantContent"];
export type Segment = Schemas["Segment"];
export type QueryCard = Schemas["QueryCard"];
export type MetricCard = Schemas["MetricCard"];
export type CleaningCard = Schemas["CleaningCard"];
export type ProposalProblem = Schemas["ProposalProblem"];
export type ActionLink = Schemas["ActionLink"];
export type ActionKind = "run-query" | "create-metric" | "cleaning-plan";

/** Clave idempotente estable por contenido: un reintento reutiliza la misma solicitud. */
function useKeys() {
  const keys = useRef(new Map<string, string>());
  return {
    get(body: unknown) {
      const signature = JSON.stringify(body);
      let key = keys.current.get(signature);
      if (!key) {
        key = crypto.randomUUID();
        keys.current.set(signature, key);
      }
      return { key, done: () => keys.current.delete(signature) };
    },
  };
}

export function useCopilotStatus(projectId: string) {
  return useQuery({
    queryKey: ["copilot-status", projectId],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/projects/{project_id}/copilot/status", {
          signal,
          params: { path: { project_id: projectId } },
        }),
      ),
  });
}

export function useConversations(projectId: string) {
  return useQuery({
    queryKey: ["copilot-conversations", projectId],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/projects/{project_id}/copilot/conversations", {
          signal,
          params: { path: { project_id: projectId } },
        }),
      ),
  });
}

export function useConversation(conversationId: string | null) {
  return useQuery({
    queryKey: ["copilot-conversation", conversationId],
    enabled: !!conversationId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/copilot/conversations/{conversation_id}", {
          signal,
          params: { path: { conversation_id: conversationId! } },
        }),
      ),
  });
}

function useRefresh(projectId: string) {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: ["copilot-conversation"] });
    void client.invalidateQueries({ queryKey: ["copilot-conversations"] });
    void client.invalidateQueries({ queryKey: ["copilot-status", projectId] });
  };
}

export function useCreateConversation(projectId: string) {
  const keys = useKeys();
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: async (title: string) => {
      const body = { title };
      const { key, done } = keys.get(body);
      const result = requireData(
        await api.POST("/api/v1/projects/{project_id}/copilot/conversations", {
          params: {
            path: { project_id: projectId },
            header: { "Idempotency-Key": key },
          },
          body,
        }),
      );
      done();
      return result;
    },
    onSuccess: refresh,
  });
}

export function useSendMessage(projectId: string) {
  const keys = useKeys();
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: async ({
      conversationId,
      versionId,
      text,
    }: {
      conversationId: string;
      versionId: string;
      text: string;
    }) => {
      const body = { version_id: versionId, text };
      const { key, done } = keys.get({ conversationId, ...body });
      const result = requireData(
        await api.POST(
          "/api/v1/copilot/conversations/{conversation_id}/messages",
          {
            params: {
              path: { conversation_id: conversationId },
              header: { "Idempotency-Key": key },
            },
            body,
          },
        ),
      );
      done();
      return result;
    },
    onSettled: refresh,
  });
}

export function useExplain(projectId: string) {
  const keys = useKeys();
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: async ({
      conversationId,
      executionId,
    }: {
      conversationId: string;
      executionId: string;
    }) => {
      const body = { execution_id: executionId };
      const { key, done } = keys.get({ conversationId, ...body });
      const result = requireData(
        await api.POST(
          "/api/v1/copilot/conversations/{conversation_id}/explanations",
          {
            params: {
              path: { conversation_id: conversationId },
              header: { "Idempotency-Key": key },
            },
            body,
          },
        ),
      );
      done();
      return result;
    },
    onSettled: refresh,
  });
}

/** Acciones explícitas sobre una propuesta: idempotentes por mensaje en el servidor. */
export function useProposalAction(projectId: string) {
  const client = useQueryClient();
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: async ({
      messageId,
      action,
    }: {
      messageId: string;
      action: ActionKind;
    }) => {
      const params = { path: { message_id: messageId } };
      const response =
        action === "run-query"
          ? await api.POST("/api/v1/copilot/messages/{message_id}/run-query", {
              params,
            })
          : action === "create-metric"
            ? await api.POST(
                "/api/v1/copilot/messages/{message_id}/create-metric",
                { params },
              )
            : await api.POST(
                "/api/v1/copilot/messages/{message_id}/cleaning-plan",
                { params },
              );
      return requireData(response);
    },
    onSuccess: (_, { action }) => {
      refresh();
      if (action === "create-metric")
        void client.invalidateQueries({ queryKey: ["metrics"] });
      if (action !== "create-metric")
        void client.invalidateQueries({ queryKey: ["plans"] });
      if (action === "run-query")
        void client.invalidateQueries({ queryKey: ["executions"] });
    },
  });
}

export const OPERATION_LABELS: Record<string, string> = {
  "cleaning.trim_whitespace": "Recortar espacios de los bordes",
  "cleaning.filter_rows": "Excluir registros",
  "cleaning.normalize_null_tokens": "Normalizar marcadores de nulo",
  "cleaning.cast": "Convertir tipo",
  "cleaning.deduplicate": "Eliminar duplicados",
};

export const UNAVAILABLE: Record<string, string> = {
  disabled:
    "La IA está desactivada en este servidor. El resto del producto funciona igual.",
  missing_key:
    "Falta configurar la clave del proveedor de IA (consulta el README).",
  budget_exhausted:
    "Se alcanzó el límite de uso del copiloto. Se renueva automáticamente.",
};

// --- Auditoría textual de un dashboard publicado (Fase 11F) --------------------------------

export type TextAudit = Schemas["TextAudit"];
export type AuditContent = Schemas["AuditContent"];

export function useTextAudits(revisionId: string) {
  return useQuery({
    queryKey: ["text-audits", revisionId],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/dashboard-revisions/{revision_id}/text-audits", {
          signal,
          params: { path: { revision_id: revisionId } },
        }),
      ),
  });
}

/** Pide la auditoría: el servidor devuelve la guardada si su clave de contenido ya existe. */
export function useRequestTextAudit(projectId: string, revisionId: string) {
  const keys = useKeys();
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { key, done } = keys.get({ revisionId });
      const result = requireData(
        await api.POST(
          "/api/v1/dashboard-revisions/{revision_id}/text-audits",
          {
            params: {
              path: { revision_id: revisionId },
              header: { "Idempotency-Key": key },
            },
          },
        ),
      );
      done();
      return result;
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ["text-audits", revisionId] });
      void client.invalidateQueries({
        queryKey: ["copilot-status", projectId],
      });
    },
  });
}
