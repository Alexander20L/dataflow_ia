import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, ApiError, requireData } from "@/lib/api";

export type AnalysisSession = components["schemas"]["AnalysisSessionView"];
export type SessionInput = components["schemas"]["SessionInput"];

/** Sesión de análisis del proyecto (Fase 11A); `null` si todavía no existe. */
export function useProjectSession(projectId: string) {
  return useQuery({
    queryKey: ["analysis-session", projectId],
    queryFn: async ({ signal }) => {
      try {
        return requireData(
          await api.GET("/api/v1/projects/{project_id}/analysis-session", {
            signal,
            params: { path: { project_id: projectId } },
          }),
        );
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    staleTime: 10000,
  });
}

export function useSessionHistory(sessionId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["analysis-session-inputs", sessionId],
    enabled: !!sessionId && enabled,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/analysis-sessions/{session_id}/inputs", {
          signal,
          params: { path: { session_id: sessionId! }, query: { limit: 20 } },
        }),
      ),
  });
}

/** Sustitución explícita de la fuente activa: abre la sesión si no existe y selecciona la
 * versión con la revisión esperada. Si la versión no está lista, la activa no cambia. */
export function useSelectSource(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      session,
      versionId,
    }: {
      session: AnalysisSession | null;
      versionId: string;
    }) => {
      const current =
        session ??
        requireData(
          await api.POST("/api/v1/projects/{project_id}/analysis-sessions", {
            params: { path: { project_id: projectId } },
          }),
        );
      return requireData(
        await api.POST("/api/v1/analysis-sessions/{session_id}/inputs", {
          params: { path: { session_id: current.id } },
          body: { version_id: versionId, expected_revision: current.revision },
        }),
      );
    },
    onSuccess: async (result) => {
      client.setQueryData(["analysis-session", projectId], result);
      await client.invalidateQueries({
        queryKey: ["analysis-session-inputs", result.id],
      });
    },
    onError: (error) => {
      // Conflicto: otra pestaña cambió la fuente; se recarga la sesión vigente.
      if (error instanceof ApiError && error.status === 409)
        void client.invalidateQueries({
          queryKey: ["analysis-session", projectId],
        });
    },
  });
}
