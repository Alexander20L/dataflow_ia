import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

export type DashboardView = components["schemas"]["DashboardView"];
export type Dashboard = NonNullable<DashboardView["dashboard"]>;
export type DashboardItem = components["schemas"]["DashboardItem"];
export type DashboardSection = components["schemas"]["DashboardSection"];
export type DashboardWidget = components["schemas"]["DashboardWidget"];
export type Indicator = components["schemas"]["Indicator"];
export type Trace = components["schemas"]["Trace"];
export type Insight = components["schemas"]["AutomaticInsight"];
export type Result = components["schemas"]["ExploreResult"];
export type FilterRequest = components["schemas"]["DashboardFilterRequest"];
export type FilterResult = components["schemas"]["DashboardFilterResult"];
export type CustomSection = components["schemas"]["CustomSection"];
export type FindingVerdict =
  components["schemas"]["FindingFeedbackRequest"]["verdict"];

/** Fase 26: el dashboard de la versión (automático, con las marcas aplicadas y la versión
 * personalizada vigente). Se consulta mientras se diseña. Sin dashboard (versiones anteriores
 * a la Fase 21) → null. */
export function useDashboardView(versionId: string) {
  return useQuery({
    queryKey: ["dashboard", versionId],
    queryFn: async ({ signal }) => {
      const result = await api.GET("/api/v1/versions/{version_id}/dashboard", {
        signal,
        params: { path: { version_id: versionId } },
      });
      if (result.response.status === 404) return null;
      return requireData(result);
    },
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.state ?? "") ? 1500 : false,
  });
}

/** Recalcula al momento, con el motor exacto, lo que depende de los filtros (no se guarda). */
export function useDashboardFilter(versionId: string) {
  return useMutation({
    mutationFn: async (body: FilterRequest) =>
      requireData(
        await api.POST("/api/v1/versions/{version_id}/dashboard/filter", {
          params: { path: { version_id: versionId } },
          body,
        }),
      ),
  });
}

/** Guarda la versión personalizada como una revisión nueva; la automática no cambia. */
export function useSaveCustomization(versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      expected_revision: number;
      sections: CustomSection[];
    }) =>
      requireData(
        await api.POST("/api/v1/versions/{version_id}/dashboard/custom", {
          params: { path: { version_id: versionId } },
          body,
        }),
      ),
    onSuccess: (view) => client.setQueryData(["dashboard", versionId], view),
  });
}

/** Marca opcional «sí va / no va»: reordena el dashboard y encola un informe nuevo. */
export function useJudgeFinding(versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      item,
      verdict,
    }: {
      item: string;
      verdict: FindingVerdict;
    }) =>
      requireData(
        await api.POST("/api/v1/versions/{version_id}/dashboard/feedback", {
          params: { path: { version_id: versionId } },
          body: { item, verdict },
        }),
      ),
    onSuccess: async (view) => {
      client.setQueryData(["dashboard", versionId], view);
      await client.invalidateQueries({ queryKey: ["progress", versionId] });
      await client.invalidateQueries({ queryKey: ["report", versionId] });
    },
  });
}
