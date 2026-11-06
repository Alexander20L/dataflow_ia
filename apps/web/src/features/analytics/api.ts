import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

export type MetricContext = components["schemas"]["MetricContext"];
export type MetricRevision = components["schemas"]["MetricRevision"];
export type MetricDraft = components["schemas"]["MetricDraft"];
export type AnalysisResult = components["schemas"]["AnalysisResult"];
export type EvidenceView = components["schemas"]["EvidenceView"];

export function useMetrics(artifactId?: string) {
  return useQuery({
    queryKey: ["metrics", artifactId],
    enabled: !!artifactId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/representations/{artifact_id}/metrics", {
          signal,
          params: { path: { artifact_id: artifactId! } },
        }),
      ),
  });
}

export function useSaveMetric(artifactId: string) {
  const client = useQueryClient();
  const keys = useRef(new Map<string, string>());
  return useMutation({
    mutationFn: async (body: components["schemas"]["SaveMetricRequest"]) => {
      const signature = JSON.stringify(body);
      let key = keys.current.get(signature);
      if (!key) {
        key = crypto.randomUUID();
        keys.current.set(signature, key);
      }
      const result = requireData(
        await api.POST("/api/v1/representations/{artifact_id}/metrics", {
          params: {
            path: { artifact_id: artifactId },
            header: { "Idempotency-Key": key },
          },
          body,
        }),
      );
      keys.current.delete(signature);
      return result;
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["metrics"] }),
  });
}

export function useAnalysisRun(runId: string | null) {
  return useQuery({
    queryKey: ["analysis-run", runId],
    enabled: !!runId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/executions/{execution_id}", {
          signal,
          params: { path: { execution_id: runId! } },
        }),
      ),
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.state ?? "queued")
        ? 1000
        : false,
  });
}

export function useAnalysisResult(runId: string | null, ready: boolean) {
  return useQuery({
    queryKey: ["analysis-result", runId],
    enabled: !!runId && ready,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/executions/{execution_id}/analysis", {
          signal,
          params: { path: { execution_id: runId! } },
        }),
      ),
    staleTime: Infinity,
  });
}

export function useEvidence(runId: string | null, evidenceId: string | null) {
  return useQuery({
    queryKey: ["evidence", runId, evidenceId],
    enabled: !!runId && !!evidenceId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET(
          "/api/v1/executions/{execution_id}/evidence/{evidence_id}",
          {
            signal,
            params: {
              path: { execution_id: runId!, evidence_id: evidenceId! },
            },
          },
        ),
      ),
    staleTime: Infinity,
  });
}
