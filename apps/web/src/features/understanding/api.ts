import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, ApiError, requireData } from "@/lib/api";

export type SemanticContext = components["schemas"]["UnderstandingContext"];
export type SemanticRevision = components["schemas"]["SemanticRevision"];
export type SemanticDraft = components["schemas"]["SemanticDraft"];
export type ColumnDraft = components["schemas"]["ColumnDraft"];
export type ReviewState = ColumnDraft["review_state"];
export const roles = {
  unknown: "Desconocido",
  identifier: "Identificador",
  dimension: "Dimensión",
  measure: "Medida",
  business_date: "Fecha de negocio",
};
export const types = {
  string: "Texto",
  integer: "Entero",
  decimal: "Decimal",
  date: "Fecha",
  boolean: "Booleano",
};
export const reviews = {
  pending: "Pendiente",
  confirmed: "Confirmado",
  rejected: "Rechazado",
};

export function useUnderstanding(id: string) {
  return useQuery({
    queryKey: ["understanding", id],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/representations/{artifact_id}/understanding", {
          signal,
          params: { path: { artifact_id: id } },
        }),
      ),
    staleTime: 10000,
    refetchOnWindowFocus: "always",
  });
}
export function useSemanticHistory(id?: string, offset = 0) {
  return useQuery({
    queryKey: ["semantic-revisions", id, offset],
    enabled: !!id,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET(
          "/api/v1/representations/{artifact_id}/semantic-contracts",
          {
            signal,
            params: {
              path: { artifact_id: id! },
              query: { limit: 20, offset },
            },
          },
        ),
      ),
  });
}
export function useSemanticRevision(id: string | null) {
  return useQuery({
    queryKey: ["semantic-revision", id],
    enabled: !!id,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/semantic-contracts/{revision_id}", {
          signal,
          params: { path: { revision_id: id! } },
        }),
      ),
    staleTime: Infinity,
  });
}
export function useSaveSemantics(id: string) {
  const client = useQueryClient();
  const keys = useRef(new Map<string, string>());
  return useMutation({
    mutationFn: async (body: components["schemas"]["SaveSemanticRequest"]) => {
      const signature = JSON.stringify(body);
      let key = keys.current.get(signature);
      if (!key) {
        key = crypto.randomUUID();
        keys.current.set(signature, key);
      }
      const result = requireData(
        await api.POST(
          "/api/v1/representations/{artifact_id}/semantic-contracts",
          {
            params: {
              path: { artifact_id: id },
              header: { "Idempotency-Key": key },
            },
            body,
          },
        ),
      );
      keys.current.delete(signature);
      return result;
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409)
        void client.invalidateQueries({ queryKey: ["understanding", id] });
    },
    onSuccess: async (result) => {
      client.setQueryData(
        ["semantic-revision", result.revision.id],
        result.revision,
      );
      await Promise.all([
        client.invalidateQueries({ queryKey: ["understanding", id] }),
        client.invalidateQueries({ queryKey: ["semantic-revisions", id] }),
      ]);
    },
  });
}

export function normalizeDraft(value: SemanticDraft) {
  return {
    ...value,
    dataset_description: value.dataset_description ?? null,
    row_grain: value.row_grain ?? {
      description: null,
      review_state: "pending" as const,
    },
    key: {
      ...(value.key ?? {
        null_policy: "reject" as const,
        review_state: "pending" as const,
      }),
      column_ids: value.key?.column_ids ?? [],
    },
    columns: value.columns.map((column) => ({
      ...column,
      null_policy: {
        ...(column.null_policy ?? { mode: "preserve" as const }),
        tokens: column.null_policy?.tokens ?? [],
      },
    })),
  };
}
export type EditorDraft = ReturnType<typeof normalizeDraft>;
export function revisionDraft(revision: SemanticRevision): EditorDraft {
  const content = revision.content;
  return normalizeDraft({
    dataset_description: content.dataset_description,
    row_grain: {
      description: content.row_grain.description,
      review_state: content.row_grain.review.state,
    },
    key: {
      column_ids: content.key.column_ids,
      null_policy: content.key.null_policy,
      review_state: content.key.review.state,
    },
    columns: content.columns.map((c) => ({
      column_id: c.id,
      description: c.description,
      interpretation_type: c.interpretation_type,
      role: c.role,
      unit: c.unit,
      currency: c.currency,
      parse_format: c.parse_format as ColumnDraft["parse_format"],
      null_policy: c.null_policy,
      review_state: c.review.state,
    })),
  });
}
