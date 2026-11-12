import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

export type ComprehensionView = components["schemas"]["ComprehensionView"];
export type Comprehension = NonNullable<ComprehensionView["comprehension"]>;
export type Relationship = components["schemas"]["Relationship"];
export type ColumnMeaning = components["schemas"]["ColumnMeaning"];
export type Formula = components["schemas"]["Formula"];
export type Verdict = components["schemas"]["FeedbackRequest"]["verdict"];

/** Fase 24: la comprensión de la versión. Se consulta mientras se calcula y mientras se rehacen
 * la exploración y el dashboard tras una validación. Las versiones anteriores a la Fase 19 no la
 * tienen (404 → null). */
export function useComprehensionView(versionId: string) {
  return useQuery({
    queryKey: ["comprehension", versionId],
    queryFn: async ({ signal }) => {
      const result = await api.GET(
        "/api/v1/versions/{version_id}/comprehension",
        { signal, params: { path: { version_id: versionId } } },
      );
      if (result.response.status === 404) return null;
      return requireData(result);
    },
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.state ?? "") ||
      q.state.data?.recalculating
        ? 1500
        : false,
  });
}

/** Validar o rechazar una relación: cuenta ya (se rehacen la exploración, el dashboard y el
 * informe) y la siguiente carga del mismo archivo también la tiene en cuenta. */
export function useJudge(versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ key, verdict }: { key: string; verdict: Verdict }) =>
      requireData(
        await api.POST("/api/v1/versions/{version_id}/comprehension/feedback", {
          params: { path: { version_id: versionId } },
          body: { relationship_key: key, verdict },
        }),
      ),
    onSuccess: (view) => {
      client.setQueryData(["comprehension", versionId], view);
      for (const key of ["exploration", "dashboard", "report"])
        void client.invalidateQueries({ queryKey: [key, versionId] });
    },
  });
}

/** Significado escrito o confirmado por el usuario: metadato que no cambia ningún cálculo. */
export function useDescribe(versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      column: string;
      meaning?: string | null;
      confirmed?: boolean;
    }) =>
      requireData(
        await api.POST("/api/v1/versions/{version_id}/comprehension/meanings", {
          params: { path: { version_id: versionId } },
          body: { ...body, confirmed: body.confirmed ?? false },
        }),
      ),
    onSuccess: (view) =>
      client.setQueryData(["comprehension", versionId], view),
  });
}
