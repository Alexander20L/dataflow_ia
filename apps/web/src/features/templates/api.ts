import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

export type TemplateCandidate = components["schemas"]["TemplateCandidate"];
export type MappingContent = components["schemas"]["MappingContent"];
export type MappingRevision = components["schemas"]["MappingRevision"];

/** Moldes candidatos de una tabla (Fase 11D): nunca confirmaciones. */
export function useTemplateCandidates(representationId: string) {
  return useQuery({
    queryKey: ["template-candidates", representationId],
    enabled: !!representationId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET(
          "/api/v1/representations/{artifact_id}/template-candidates",
          { signal, params: { path: { artifact_id: representationId } } },
        ),
      ).candidates,
  });
}

export function useMappings(projectId: string) {
  return useQuery({
    queryKey: ["template-mappings", projectId],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/projects/{project_id}/template-mappings", {
          signal,
          params: { path: { project_id: projectId } },
        }),
      ).items,
  });
}

/** Guarda la interpretación confirmada (revisión inmutable por proyecto y molde). */
export function useSaveMapping(projectId: string) {
  const client = useQueryClient();
  const keys = useRef(new Map<string, string>());
  return useMutation({
    mutationFn: async ({
      expected,
      content,
    }: {
      expected: number;
      content: MappingContent;
    }) => {
      const signature = JSON.stringify({ expected, content });
      let key = keys.current.get(signature);
      if (!key) {
        key = crypto.randomUUID();
        keys.current.set(signature, key);
      }
      return requireData(
        await api.POST("/api/v1/projects/{project_id}/template-mappings", {
          params: {
            path: { project_id: projectId },
            header: { "Idempotency-Key": key },
          },
          body: { expected_revision: expected, content },
        }),
      );
    },
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({
          queryKey: ["template-mappings", projectId],
        }),
        client.invalidateQueries({ queryKey: ["template-candidates"] }),
      ]),
  });
}
