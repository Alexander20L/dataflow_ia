import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

export type DatasetVersion = components["schemas"]["VersionResponse"];
export type Diagnostic = components["schemas"]["Diagnostic"];
export function useIngestionSummary() {
  return useQuery({
    queryKey: ["ingestion-summary"],
    queryFn: async ({ signal }) =>
      requireData(await api.GET("/api/v1/datasets/summary", { signal })),
    refetchInterval: 5000,
  });
}
export function useVersions(projectId: string, offset = 0) {
  return useQuery({
    queryKey: ["versions", projectId, offset],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/projects/{project_id}/versions", {
          signal,
          params: {
            path: { project_id: projectId },
            query: { limit: 20, offset },
          },
        }),
      ),
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (v) => v.state === "queued" || v.state === "processing",
      )
        ? 1000
        : false,
  });
}
/** Una versión por ID: para seleccionar o nombrar versiones que no están en la página cargada. */
export function useVersion(versionId?: string) {
  return useQuery({
    queryKey: ["version", versionId],
    enabled: Boolean(versionId),
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/versions/{version_id}", {
          signal,
          params: { path: { version_id: versionId! } },
        }),
      ),
    refetchInterval: (query) =>
      ["queued", "processing"].includes(query.state.data?.state ?? "")
        ? 1000
        : false,
  });
}
export const XLSX_MIME =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
export const isXlsx = (file: File) => /\.xlsx$/i.test(file.name);
export const isPdf = (file: File) => /\.pdf$/i.test(file.name);

/** Sube un CSV o un .xlsx sin opciones: el sistema detecta el separador o elige la hoja,
 * la tabla y la cabecera (Fase 13B) y lo informa en la versión. */
export function useUploadFile(projectId = "") {
  const client = useQueryClient();
  const keys = useRef(new WeakMap<File, string>());
  return useMutation({
    mutationFn: async ({
      file,
      projectId: targetProject,
    }: {
      file: File;
      projectId?: string;
    }) => {
      const target = targetProject ?? projectId;
      let key = keys.current.get(file);
      if (!key) {
        key = crypto.randomUUID();
        keys.current.set(file, key);
      }
      const version = requireData(
        isPdf(file)
          ? await api.POST("/api/v1/projects/{project_id}/imports/pdf", {
              params: {
                path: { project_id: target },
                query: { file_name: file.name },
                header: { "Idempotency-Key": key },
              },
              headers: { "Content-Type": "application/pdf" },
              body: file,
              bodySerializer: (body) => body,
            })
          : isXlsx(file)
            ? await api.POST("/api/v1/projects/{project_id}/imports/xlsx", {
                params: {
                  path: { project_id: target },
                  query: { file_name: file.name },
                  header: { "Idempotency-Key": key },
                },
                headers: { "Content-Type": XLSX_MIME },
                body: file,
                bodySerializer: (body) => body,
              })
            : await api.POST("/api/v1/projects/{project_id}/imports", {
                params: {
                  path: { project_id: target },
                  query: { file_name: file.name, separator: "auto" },
                  header: { "Idempotency-Key": key },
                },
                headers: { "Content-Type": "text/csv" },
                body: file,
                bodySerializer: (body) => body,
              }),
      );
      keys.current.delete(file);
      return version;
    },
    onSuccess: async (version) => {
      await client.invalidateQueries({
        queryKey: ["versions", version.project_id],
      });
    },
  });
}
export function useDiagnostic(version?: DatasetVersion) {
  return useQuery({
    queryKey: ["diagnostic", version?.id],
    enabled: version?.state === "succeeded",
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/versions/{version_id}/diagnostic", {
          signal,
          params: { path: { version_id: version!.id } },
        }),
      ),
    staleTime: Infinity,
  });
}
export function usePreview(
  version?: DatasetVersion,
  page = 0,
  issueId?: string,
) {
  return useQuery({
    queryKey: ["preview", version?.id, page, issueId],
    enabled: version?.state === "succeeded",
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/versions/{version_id}/preview", {
          signal,
          params: {
            path: { version_id: version!.id },
            query: { limit: 10, offset: page * 10, issue_id: issueId },
          },
        }),
      ),
    staleTime: Infinity,
  });
}
export function useCancelImport(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (executionId: string) =>
      requireData(
        await api.POST("/api/v1/executions/{execution_id}/cancel", {
          params: { path: { execution_id: executionId } },
        }),
      ),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["versions", projectId] });
    },
  });
}
export type AutomaticAnalysis = components["schemas"]["AutomaticAnalysis"];
// Fase 15: plan analítico y hallazgos guardados al importar. Las versiones anteriores no lo
// tienen (404 AUTOMATIC_ANALYSIS_NOT_AVAILABLE): se muestra sólo el dashboard descriptivo.
export function useAutomaticAnalysis(version?: DatasetVersion) {
  return useQuery({
    queryKey: ["automatic-analysis", version?.id],
    enabled: version?.state === "succeeded",
    queryFn: async ({ signal }) => {
      const result = await api.GET(
        "/api/v1/versions/{version_id}/automatic-analysis",
        { signal, params: { path: { version_id: version!.id } } },
      );
      if (result.response.status === 404) return null;
      return requireData(result);
    },
    staleTime: Infinity,
  });
}

export type Investigation = components["schemas"]["Investigation"];
export type InvestigationView = components["schemas"]["InvestigationView"];
// Fase 16: investigación automática tras la carga (reglas + propuestas de la IA validadas).
// Las versiones anteriores no la tienen (404 INVESTIGATION_NOT_AVAILABLE): se muestra la
// explicación del dashboard como antes.
export function useInvestigation(version?: DatasetVersion) {
  return useQuery({
    queryKey: ["investigation", version?.id],
    enabled: version?.state === "succeeded",
    queryFn: async ({ signal }) => {
      const result = await api.GET(
        "/api/v1/versions/{version_id}/investigation",
        {
          signal,
          params: { path: { version_id: version!.id } },
        },
      );
      if (result.response.status === 404) return null;
      return requireData(result);
    },
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.state ?? "") ? 1000 : false,
  });
}

export type VersionProgress = components["schemas"]["Progress"];

// Fase 17: etapas de la carga (análisis, investigación e informe); se consulta mientras
// alguna siga pendiente.
export function useProgress(version?: DatasetVersion) {
  return useQuery({
    queryKey: ["progress", version?.id],
    enabled: version?.state === "succeeded",
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/versions/{version_id}/progress", {
          signal,
          params: { path: { version_id: version!.id } },
        }),
      ),
    refetchInterval: (q) => (q.state.data?.complete === false ? 1500 : false),
  });
}

export type SourceReview = components["schemas"]["SourceReview"];

// Fase 18: cómo se leyó el archivo (codificación, separador, valores regionales) y qué
// columnas cambiaron respecto de la versión anterior del mismo archivo.
export function useSourceReview(version?: DatasetVersion) {
  return useQuery({
    queryKey: ["source-review", version?.id],
    enabled: version?.state === "succeeded",
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/versions/{version_id}/reading", {
          signal,
          params: { path: { version_id: version!.id } },
        }),
      ),
    staleTime: Infinity,
  });
}

export type SqlServerConnection = components["schemas"]["SqlServerConnection"];

// Fase 18B: copia de un solo uso de las tablas de una base de SQL Server. La contraseña viaja
// sólo en esta petición; el servidor no la guarda.
export function useImportSqlServer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      projectId,
      connection,
    }: {
      projectId: string;
      connection: SqlServerConnection;
    }) =>
      requireData(
        await api.POST("/api/v1/projects/{project_id}/imports/sqlserver", {
          params: {
            path: { project_id: projectId },
            header: { "Idempotency-Key": crypto.randomUUID() },
          },
          body: connection,
        }),
      ),
    onSuccess: async (version) => {
      await client.invalidateQueries({
        queryKey: ["versions", version.project_id],
      });
    },
  });
}

export type ReportView = components["schemas"]["ReportView"];

// Fase 21: estado del informe (se sigue sirviendo el anterior mientras se genera uno nuevo).
export function useReport(versionId: string, watch: boolean) {
  return useQuery({
    queryKey: ["report", versionId],
    enabled: watch,
    queryFn: async ({ signal }) => {
      const result = await api.GET("/api/v1/versions/{version_id}/report", {
        signal,
        params: { path: { version_id: versionId } },
      });
      if (result.response.status === 404) return null;
      return requireData(result);
    },
    refetchInterval: (q) =>
      q.state.data?.updating ||
      ["queued", "running"].includes(q.state.data?.state ?? "")
        ? 1500
        : false,
  });
}
