import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

export type DatasetVersion = components["schemas"]["VersionResponse"];
export type Diagnostic = components["schemas"]["Diagnostic"];
export type Separator = "auto" | "," | ";" | "tab";
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
export function useUploadCsv(projectId = "") {
  const client = useQueryClient();
  const keys = useRef(new WeakMap<File, Map<Separator, string>>());
  return useMutation({
    mutationFn: async ({
      file,
      separator = "auto",
      projectId: targetProject,
    }: {
      file: File;
      separator?: Separator;
      projectId?: string;
    }) => {
      const target = targetProject ?? projectId;
      let map = keys.current.get(file);
      if (!map) {
        map = new Map();
        keys.current.set(file, map);
      }
      let key = map.get(separator);
      if (!key) {
        key = crypto.randomUUID();
        map.set(separator, key);
      }
      const version = requireData(
        await api.POST("/api/v1/projects/{project_id}/imports", {
          params: {
            path: { project_id: target },
            query: { file_name: file.name, separator },
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

export const XLSX_MIME =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
export type XlsxInspection = components["schemas"]["XlsxInspection"];
export type XlsxSelection = {
  sheet?: string;
  table?: string | null;
  header_row: number;
};

/** Fase 12A: hojas, tablas y vista previa de la selección; no guarda nada. */
export function useInspectXlsx(projectId: string) {
  return useMutation({
    mutationFn: async ({
      file,
      selection,
    }: {
      file: File;
      selection: XlsxSelection;
    }) =>
      requireData(
        await api.POST("/api/v1/projects/{project_id}/imports/xlsx/inspect", {
          params: {
            path: { project_id: projectId },
            query: {
              file_name: file.name,
              sheet: selection.sheet,
              table: selection.table ?? undefined,
              header_row: selection.header_row,
            },
          },
          headers: { "Content-Type": XLSX_MIME },
          body: file,
          bodySerializer: (body) => body,
        }),
      ),
  });
}

export function useUploadXlsx(projectId: string) {
  const client = useQueryClient();
  const keys = useRef(new WeakMap<File, Map<string, string>>());
  return useMutation({
    mutationFn: async ({
      file,
      selection,
    }: {
      file: File;
      selection: Required<XlsxSelection>;
    }) => {
      const signature = JSON.stringify(selection);
      let map = keys.current.get(file);
      if (!map) {
        map = new Map();
        keys.current.set(file, map);
      }
      let key = map.get(signature);
      if (!key) {
        key = crypto.randomUUID();
        map.set(signature, key);
      }
      const version = requireData(
        await api.POST("/api/v1/projects/{project_id}/imports/xlsx", {
          params: {
            path: { project_id: projectId },
            query: {
              file_name: file.name,
              sheet: selection.sheet,
              table: selection.table ?? undefined,
              header_row: selection.header_row,
            },
            header: { "Idempotency-Key": key },
          },
          headers: { "Content-Type": XLSX_MIME },
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
