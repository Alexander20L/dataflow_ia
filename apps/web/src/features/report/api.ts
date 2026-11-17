import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

export type ReportView = components["schemas"]["ReportView"];
export type ReportDocument = components["schemas"]["ReportDocument"];
export type ReportSection = components["schemas"]["ReportSection"];
export type ReportBlock = components["schemas"]["ReportBlock"];
export type ReviewItem = components["schemas"]["ReviewItem"];
export type ReviewStatus = ReviewItem["status"];
export type ReportVersion = components["schemas"]["ReportVersion"];

/** Fase 27: el informe de la versión (el último o, con `executionId`, uno del historial). Se
 * consulta mientras se genera. Sin informe → null. */
export function useReportView(versionId: string, executionId?: string) {
  return useQuery({
    queryKey: ["report", versionId, executionId ?? "latest"],
    queryFn: async ({ signal }) => {
      const result = executionId
        ? await api.GET(
            "/api/v1/versions/{version_id}/report/versions/{execution_id}",
            {
              signal,
              params: {
                path: { version_id: versionId, execution_id: executionId },
              },
            },
          )
        : await api.GET("/api/v1/versions/{version_id}/report", {
            signal,
            params: { path: { version_id: versionId } },
          });
      if (result.response.status === 404) return null;
      return requireData(result);
    },
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.state ?? "") ||
      q.state.data?.updating
        ? 1500
        : false,
  });
}

export function useReportHistory(versionId: string) {
  return useQuery({
    queryKey: ["report-history", versionId],
    queryFn: async ({ signal }) => {
      const result = await api.GET(
        "/api/v1/versions/{version_id}/report/history",
        { signal, params: { path: { version_id: versionId } } },
      );
      if (result.response.status === 404) return null;
      return requireData(result);
    },
    refetchInterval: (q) =>
      (q.state.data?.items ?? []).some((i) =>
        ["queued", "running"].includes(i.state),
      )
        ? 1500
        : false,
  });
}

/** Hallazgos candidatos con su revisión. 409 si el informe es anterior a la Fase 27 → null. */
export function useReportReview(versionId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["report-review", versionId],
    enabled,
    queryFn: async ({ signal }) => {
      const result = await api.GET(
        "/api/v1/versions/{version_id}/report/review",
        { signal, params: { path: { version_id: versionId } } },
      );
      if ([404, 409].includes(result.response.status)) return null;
      return requireData(result);
    },
  });
}

/** Aprobar, rechazar o dejar pendiente un hallazgo (no genera el informe). */
export function useReviewFinding(versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: { item: string; status: ReviewStatus }) =>
      requireData(
        await api.POST("/api/v1/versions/{version_id}/report/review", {
          params: { path: { version_id: versionId } },
          body,
        }),
      ),
    onSuccess: async (review) => {
      client.setQueryData(["report-review", versionId], review);
      await client.invalidateQueries({ queryKey: ["dashboard", versionId] });
    },
  });
}

/** Genera una versión nueva del informe con la selección vigente; la anterior se conserva. */
export function useGenerateReport(versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      requireData(
        await api.POST("/api/v1/versions/{version_id}/report/versions", {
          params: { path: { version_id: versionId } },
        }),
      ),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["report", versionId] });
      await client.invalidateQueries({
        queryKey: ["report-history", versionId],
      });
      await client.invalidateQueries({ queryKey: ["progress", versionId] });
    },
  });
}
