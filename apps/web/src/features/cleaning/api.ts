import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

export type CleaningPreview = components["schemas"]["PreviewView"];
export type Approval = components["schemas"]["ApprovalView"];
export type EffectSample = components["schemas"]["EffectSample"];
export type EffectCounts = components["schemas"]["EffectCounts"];

export type CleaningProposal = components["schemas"]["CleaningProposal"];

const running = (state?: string) => state === "queued" || state === "running";

/** Propuesta inicial de limpieza calculada en el servidor (Fase 11A). */
export function useCleaningProposal(representationId: string) {
  return useQuery({
    queryKey: ["cleaning-proposal", representationId],
    enabled: !!representationId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET(
          "/api/v1/representations/{artifact_id}/cleaning-proposal",
          { signal, params: { path: { artifact_id: representationId } } },
        ),
      ),
    staleTime: 10000,
    refetchOnWindowFocus: "always",
  });
}

export function useCleaningPreview(executionId: string | null) {
  return useQuery({
    queryKey: ["cleaning-preview", executionId],
    enabled: !!executionId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/previews/{execution_id}", {
          signal,
          params: { path: { execution_id: executionId! } },
        }),
      ),
    refetchInterval: (query) =>
      running(query.state.data?.state) ||
      running(query.state.data?.apply?.state)
        ? 1000
        : false,
  });
}
export function useCreatePreview() {
  const keys = useRef(new Map<string, string>());
  return useMutation({
    mutationFn: async (revisionId: string) => {
      let key = keys.current.get(revisionId);
      if (!key) {
        key = crypto.randomUUID();
        keys.current.set(revisionId, key);
      }
      const run = requireData(
        await api.POST("/api/v1/plans/{revision_id}/previews", {
          params: {
            path: { revision_id: revisionId },
            header: { "Idempotency-Key": key },
          },
        }),
      );
      keys.current.delete(revisionId);
      return run;
    },
  });
}
export function useApprove(executionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (effectSha256: string) =>
      requireData(
        await api.POST("/api/v1/previews/{execution_id}/approvals", {
          params: { path: { execution_id: executionId } },
          body: { effect_sha256: effectSha256 },
        }),
      ),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["cleaning-preview", executionId] }),
  });
}
export function useRevoke(executionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (approvalId: string) =>
      requireData(
        await api.POST("/api/v1/approvals/{approval_id}/revoke", {
          params: { path: { approval_id: approvalId } },
        }),
      ),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["cleaning-preview", executionId] }),
  });
}
export function useApply(executionId: string, projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (approvalId: string) =>
      requireData(
        await api.POST("/api/v1/approvals/{approval_id}/apply", {
          params: { path: { approval_id: approvalId } },
        }),
      ),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({
          queryKey: ["cleaning-preview", executionId],
        }),
        client.invalidateQueries({ queryKey: ["versions", projectId] }),
      ]);
    },
  });
}
export function useLineage(versionId?: string, enabled = true) {
  return useQuery({
    queryKey: ["lineage", versionId],
    enabled: !!versionId && enabled,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/versions/{version_id}/lineage", {
          signal,
          params: { path: { version_id: versionId! } },
        }),
      ),
    staleTime: Infinity,
  });
}

/** Texto de un valor de celda: los nulos se muestran explícitamente. */
export function cell(value: string | null | undefined) {
  if (value === null || value === undefined) return "nulo";
  if (value.trim() === "")
    return `«${value.replace(/\t/g, "⇥")}» (sólo espacios)`;
  return value;
}
