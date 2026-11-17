import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

export type InvestigationView = components["schemas"]["ExplorationView"];
export type Investigation = NonNullable<InvestigationView["exploration"]>;
export type InvestigationNode = components["schemas"]["InvestigationNode"];
export type InvestigationResult = components["schemas"]["ExploreResult"];
export type InvestigationRun = components["schemas"]["InvestigationRun"];
export type Command = components["schemas"]["InvestigationCommand"]["action"];

/** Fase 25: la investigación de la versión (la última o, con `executionId`, una anterior del
 * historial). Se consulta mientras está en cola o en marcha. Sin investigación (versiones
 * anteriores a la Fase 20) → null. */
export function useInvestigationView(versionId: string, executionId?: string) {
  return useQuery({
    queryKey: ["exploration", versionId, executionId ?? "latest"],
    queryFn: async ({ signal }) => {
      const result = await api.GET(
        "/api/v1/versions/{version_id}/exploration",
        {
          signal,
          params: {
            path: { version_id: versionId },
            query: executionId ? { execution_id: executionId } : {},
          },
        },
      );
      if (result.response.status === 404) return null;
      return requireData(result);
    },
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.state ?? "") ? 1500 : false,
  });
}

export function useInvestigationHistory(versionId: string) {
  return useQuery({
    queryKey: ["exploration-history", versionId],
    queryFn: async ({ signal }) => {
      const result = await api.GET(
        "/api/v1/versions/{version_id}/exploration/history",
        { signal, params: { path: { version_id: versionId } } },
      );
      if (result.response.status === 404) return null;
      return requireData(result);
    },
  });
}

/** Pausar, cancelar, reanudar o volver a investigar. Lo anterior se conserva; al terminar se
 * rehacen el dashboard y el informe. */
export function useInvestigationControl(versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (action: Command) =>
      requireData(
        await api.POST("/api/v1/versions/{version_id}/exploration/control", {
          params: { path: { version_id: versionId } },
          body: { action },
        }),
      ),
    onSuccess: (view) => {
      client.setQueryData(["exploration", versionId, "latest"], view);
      for (const key of ["exploration-history", "dashboard", "progress"])
        void client.invalidateQueries({ queryKey: [key, versionId] });
    },
  });
}
