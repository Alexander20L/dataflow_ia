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
