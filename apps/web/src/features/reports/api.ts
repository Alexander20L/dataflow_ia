import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

type Schemas = components["schemas"];
export type ReportView = Schemas["ReportView"];
export type ReportDraft = Schemas["ReportDraft"];
export type ReportRevision = Schemas["ReportRevision"];
export type Provenance = Schemas["Provenance"];
export type Block = NonNullable<ReportDraft["blocks"]>[number];
export type PdfRender = Schemas["PdfRender"];

function useKeys() {
  const keys = useRef(new Map<string, string>());
  return {
    get(body: unknown) {
      const signature = JSON.stringify(body);
      let key = keys.current.get(signature);
      if (!key) {
        key = crypto.randomUUID();
        keys.current.set(signature, key);
      }
      return { key, done: () => keys.current.delete(signature) };
    },
  };
}

function useInvalidate() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: ["reports"] });
    void client.invalidateQueries({ queryKey: ["report"] });
    void client.invalidateQueries({ queryKey: ["report-revisions"] });
    void client.invalidateQueries({ queryKey: ["report-pdfs"] });
  };
}

export function useReports(projectId: string) {
  return useQuery({
    queryKey: ["reports", projectId],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/projects/{project_id}/reports", {
          signal,
          params: { path: { project_id: projectId } },
        }),
      ),
  });
}

export function useReport(familyId: string | null, revisionId: string | null) {
  return useQuery({
    queryKey: ["report", familyId, revisionId],
    enabled: !!familyId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/reports/{family_id}", {
          signal,
          params: {
            path: { family_id: familyId! },
            query: revisionId ? { revision: revisionId } : {},
          },
        }),
      ),
    refetchInterval: (query) =>
      query.state.data?.provenance.some((p) => p.status === "pending")
        ? 1500
        : false,
  });
}

export function useReportRevisions(familyId: string | null) {
  return useQuery({
    queryKey: ["report-revisions", familyId],
    enabled: !!familyId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/reports/{family_id}/revisions", {
          signal,
          params: { path: { family_id: familyId! } },
        }),
      ),
  });
}

export function useReportPdfs(familyId: string | null) {
  return useQuery({
    queryKey: ["report-pdfs", familyId],
    enabled: !!familyId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/reports/{family_id}/pdfs", {
          signal,
          params: { path: { family_id: familyId! } },
        }),
      ),
    refetchInterval: (query) =>
      query.state.data?.some((r) => ["queued", "running"].includes(r.state))
        ? 1500
        : false,
  });
}

export function useCreateReport(projectId: string) {
  const keys = useKeys();
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (body: { version_id: string; draft: ReportDraft }) => {
      const { key, done } = keys.get(body);
      const result = requireData(
        await api.POST("/api/v1/projects/{project_id}/reports", {
          params: {
            path: { project_id: projectId },
            header: { "Idempotency-Key": key },
          },
          body,
        }),
      );
      done();
      return result;
    },
    onSuccess: invalidate,
  });
}

export function useReviseReport() {
  const keys = useKeys();
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async ({
      familyId,
      expected,
      draft,
    }: {
      familyId: string;
      expected: number;
      draft: ReportDraft;
    }) => {
      const body = { expected_revision: expected, draft };
      const { key, done } = keys.get({ familyId, ...body });
      const result = requireData(
        await api.POST("/api/v1/reports/{family_id}/revisions", {
          params: {
            path: { family_id: familyId },
            header: { "Idempotency-Key": key },
          },
          body,
        }),
      );
      done();
      return result;
    },
    onSuccess: invalidate,
  });
}

export function useRefreshReport() {
  const keys = useKeys();
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async ({
      familyId,
      expected,
      versionId,
    }: {
      familyId: string;
      expected: number;
      versionId: string;
    }) => {
      const body = { expected_revision: expected, version_id: versionId };
      const { key, done } = keys.get({ familyId, ...body });
      const result = requireData(
        await api.POST("/api/v1/reports/{family_id}/refresh", {
          params: {
            path: { family_id: familyId },
            header: { "Idempotency-Key": key },
          },
          body,
        }),
      );
      done();
      return result;
    },
    onSuccess: invalidate,
  });
}

export function useRenderPdf() {
  const keys = useKeys();
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (revisionId: string) => {
      const { key, done } = keys.get({ revisionId });
      const result = requireData(
        await api.POST("/api/v1/report-revisions/{revision_id}/pdf", {
          params: {
            path: { revision_id: revisionId },
            header: { "Idempotency-Key": key },
          },
        }),
      );
      done();
      return result;
    },
    onSuccess: invalidate,
  });
}

export const BLOCK_LABELS: Record<Block["kind"] & string, string> = {
  text: "Texto",
  conclusion: "Conclusión",
  limitations: "Limitaciones",
  analysis: "Resultado de análisis",
  dashboard_card: "Tarjeta de dashboard",
};
