import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { ApiError, api, requireData } from "@/lib/api";

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
// Fase 27: las cargas nuevas ya no tienen seguimiento (Fase 16); sólo se consulta si la
// versión tiene ese trabajo (`followed`, de su progreso).
export function useInvestigation(version?: DatasetVersion, followed = true) {
  return useQuery({
    queryKey: ["investigation", version?.id],
    enabled: version?.state === "succeeded" && followed,
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
export type PostgresConnection = components["schemas"]["PostgresConnection"];
export type DatabaseEngine = "sqlserver" | "postgresql";
export type DatabaseAccess = components["schemas"]["DatabaseAccess"];
export type DatabaseCopy = components["schemas"]["DatabaseCopy"];

/** Fase 33: la copia de una base sigue en segundo plano; se consulta cada pocos segundos hasta
 * que termina. Una copia fallida se convierte en un error con su motivo. */
async function finishedCopy(copy: DatabaseCopy): Promise<DatabaseCopy> {
  let current = copy;
  while (current.state === "queued" || current.state === "running") {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    current = requireData(
      await api.GET("/api/v1/database-copies/{copy_id}", {
        params: { path: { copy_id: current.id } },
      }),
    );
  }
  if (current.state === "failed")
    throw new ApiError(
      current.error_message ?? "No se pudo copiar la base.",
      422,
    );
  return current;
}

/** Fase 32: a qué bases se puede conectar en este entorno (lista, modo público o ninguna) y,
 * en el modo público, desde qué direcciones sale DataFlow. */
export function useDatabaseAccess() {
  return useQuery({
    queryKey: ["database-access"],
    queryFn: async ({ signal }) =>
      requireData(await api.GET("/api/v1/database-access", { signal })),
    staleTime: 5 * 60 * 1000,
  });
}

/** Fase 18B, 31 y 33: copia de un solo uso de todas las tablas de una base (SQL Server o
 * PostgreSQL), en segundo plano. Devuelve la copia terminada: su `version_id` es la versión
 * principal (la tabla unida si las tablas se relacionan). */
export function useImportDatabase() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (
      request:
        | {
            engine: "sqlserver";
            projectId: string;
            connection: SqlServerConnection;
          }
        | {
            engine: "postgresql";
            projectId: string;
            connection: PostgresConnection;
          },
    ) => {
      const params = {
        path: { project_id: request.projectId },
        header: { "Idempotency-Key": crypto.randomUUID() },
      };
      return finishedCopy(
        requireData(
          request.engine === "sqlserver"
            ? await api.POST(
                "/api/v1/projects/{project_id}/imports/sqlserver",
                {
                  params,
                  body: request.connection,
                },
              )
            : await api.POST(
                "/api/v1/projects/{project_id}/imports/postgresql",
                { params, body: request.connection },
              ),
        ),
      );
    },
    onSuccess: async (copy) => {
      await client.invalidateQueries({
        queryKey: ["versions", copy.project_id],
      });
    },
  });
}

export type DataModel = components["schemas"]["DataModel"];

/** Fase 31: «foto» del esquema de una base (tablas, claves, relaciones y vistas) sin guardar
 * nada; la contraseña se usa para leer y se descarta. */
export function useInspectDatabase() {
  return useMutation({
    mutationFn: async (
      request:
        | {
            engine: "sqlserver";
            projectId: string;
            connection: SqlServerConnection;
          }
        | {
            engine: "postgresql";
            projectId: string;
            connection: PostgresConnection;
          },
    ): Promise<DataModel> => {
      const params = { path: { project_id: request.projectId } };
      const copy = await finishedCopy(
        requireData(
          request.engine === "sqlserver"
            ? await api.POST(
                "/api/v1/projects/{project_id}/imports/sqlserver/inspect",
                { params, body: request.connection },
              )
            : await api.POST(
                "/api/v1/projects/{project_id}/imports/postgresql/inspect",
                { params, body: request.connection },
              ),
        ),
      );
      if (!copy.model) throw new ApiError("No se pudo leer el esquema.", 422);
      return copy.model;
    },
  });
}

/** Fase 31: «foto» del modelo de datos de los archivos sin guardar nada. */
export function useInspectRelated() {
  return useMutation({
    // Sin proyecto: «Ver esquema» no crea nada si la persona no continúa (defecto D-02).
    mutationFn: async ({ files }: { files: File[] }): Promise<DataModel> =>
      requireData(
        await api.POST("/api/v1/imports/related/inspect", {
          body: { files: await encodeFiles(files) },
        }),
      ),
  });
}

async function encodeFiles(files: File[]) {
  return Promise.all(
    files.map(async (file) => ({
      name: file.name,
      content_base64: await toBase64(file),
    })),
  );
}

async function toBase64(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000)
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

/** Fase 31: de 2 a 5 archivos relacionados en una sola carga. Cada uno se analiza por separado
 * y, si comparten claves, también unidos (`relations-v1`). La clave de idempotencia se conserva
 * mientras la selección no cambie (un reintento no duplica la carga). */
export function useUploadRelated() {
  const client = useQueryClient();
  const keys = useRef(new Map<string, string>());
  return useMutation({
    mutationFn: async ({
      files,
      projectId,
    }: {
      files: File[];
      projectId: string;
    }) => {
      const signature = `${projectId}|${files
        .map((f) => `${f.name}:${f.size}:${f.lastModified}`)
        .join("|")}`;
      let key = keys.current.get(signature);
      if (!key) {
        key = crypto.randomUUID();
        keys.current.set(signature, key);
      }
      const body = { files: await encodeFiles(files) };
      return requireData(
        await api.POST("/api/v1/projects/{project_id}/imports/related", {
          params: {
            path: { project_id: projectId },
            header: { "Idempotency-Key": key },
          },
          body,
        }),
      );
    },
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
