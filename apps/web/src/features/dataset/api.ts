import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

export type InspectionView = components["schemas"]["InspectionView"];
export type Inspection = components["schemas"]["Inspection"];
export type ColumnInspection = components["schemas"]["ColumnInspection"];
export type DictionaryEntry = components["schemas"]["DictionaryEntry"];
export type Finding = components["schemas"]["Finding"];
export type AnnotationRequest = components["schemas"]["AnnotationRequest"];
export type RecordsPage = components["schemas"]["RecordsPage"];

/** Fase 22: inspección calculada una vez al cargar; mientras se calcula se consulta cada segundo. */
export function useInspection(versionId?: string, enabled = true) {
  return useQuery({
    queryKey: ["inspection", versionId],
    enabled: Boolean(versionId) && enabled,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/versions/{version_id}/inspection", {
          signal,
          params: { path: { version_id: versionId! } },
        }),
      ),
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.state ?? "")
        ? 1000
        : false,
  });
}

export type RecordQuery = {
  page: number;
  size: number;
  sort?: string;
  descending: boolean;
  search?: string;
};

/** Registros paginados, ordenados y buscados en el servidor: nunca se descarga la tabla entera. */
export function useRecords(versionId: string, query: RecordQuery) {
  return useQuery({
    queryKey: ["records", versionId, query],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/versions/{version_id}/preview", {
          signal,
          params: {
            path: { version_id: versionId },
            query: {
              limit: query.size,
              offset: query.page * query.size,
              sort: query.sort,
              descending: query.descending,
              search: query.search || undefined,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  });
}

/** Corrección manual del diccionario: metadato que no cambia el archivo ni los cálculos. */
export function useAnnotate(versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: AnnotationRequest) =>
      requireData(
        await api.POST("/api/v1/versions/{version_id}/dictionary", {
          params: { path: { version_id: versionId } },
          body,
        }),
      ),
    onSuccess: (view) => client.setQueryData(["inspection", versionId], view),
  });
}
