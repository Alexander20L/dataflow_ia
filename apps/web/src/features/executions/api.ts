import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

export type Execution = components["schemas"]["ExecutionResponse"];
export function useVersionExecutions(versionId: string) {
  return useQuery({
    queryKey: ["executions", versionId],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/versions/{version_id}/executions", {
          signal,
          params: { path: { version_id: versionId } },
        }),
      ),
    refetchInterval: (query) =>
      query.state.data?.some(
        (run) => run.state === "queued" || run.state === "running",
      )
        ? 1000
        : false,
  });
}
export function useRepresentations(versionId: string) {
  return useQuery({
    queryKey: ["representations", versionId],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/versions/{version_id}/representations", {
          signal,
          params: { path: { version_id: versionId } },
        }),
      ),
    staleTime: 15000,
  });
}
export function useExecution(run?: Execution) {
  return useQuery({
    queryKey: ["execution", run?.id, run?.state, run?.attempts],
    enabled: !!run,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/executions/{execution_id}", {
          signal,
          params: { path: { execution_id: run!.id } },
        }),
      ),
  });
}
export function useExecutionQuality(run?: Execution) {
  return useQuery({
    queryKey: ["execution-quality", run?.id],
    enabled: run?.state === "succeeded",
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/executions/{execution_id}/quality", {
          signal,
          params: { path: { execution_id: run!.id } },
        }),
      ),
    staleTime: Infinity,
  });
}
export function useCancelExecution(versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (executionId: string) =>
      requireData(
        await api.POST("/api/v1/executions/{execution_id}/cancel-analysis", {
          params: { path: { execution_id: executionId } },
        }),
      ),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["executions", versionId] });
    },
  });
}
