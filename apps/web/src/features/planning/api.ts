import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, ApiError, requireData } from "@/lib/api";

export type Plan = components["schemas"]["PlanView"];
export type PlanStep = components["schemas"]["PlanStep"];
export type Problem = components["schemas"]["Problem"];
export type Operation = components["schemas"]["OperationResponse"];
export type ApplicableOperation = components["schemas"]["ApplicableOperation"];
export type SemanticRef = NonNullable<Plan["semantic_ref"]>;
export type PlanDraft = {
  semantic_ref: SemanticRef | null;
  steps: PlanStep[];
};

export const problemLabels: Record<Problem["code"], string> = {
  EMPTY_PLAN: "Plan vacío",
  TOO_MANY_STEPS: "Demasiados pasos",
  DUPLICATE_STEP_ID: "Paso repetido",
  INVALID_STEP_REFERENCE: "Referencia no válida",
  UNSUPPORTED_OPERATION: "Operación no disponible",
  INPUT_KIND_MISMATCH: "Entrada incompatible",
  INVALID_PARAMETERS: "Parámetros incompletos",
  UNKNOWN_COLUMN: "Columna inexistente",
  SEMANTIC_REQUIREMENT_MISSING: "Requisito semántico pendiente",
  COLUMN_TYPE_MISMATCH: "Tipo de columna incompatible",
  IDENTIFIER_CONVERSION_UNCONFIRMED:
    "Conversión de identificador sin confirmar",
  QUALITY_RULESET_MISMATCH: "Reglas de calidad no válidas",
};

/** Clave idempotente estable por contenido: un reintento reutiliza la misma solicitud. */
function useIdempotencyKeys() {
  const keys = useRef(new Map<string, string>());
  return {
    get(signature: string) {
      let key = keys.current.get(signature);
      if (!key) {
        key = crypto.randomUUID();
        keys.current.set(signature, key);
      }
      return key;
    },
    done(signature: string) {
      keys.current.delete(signature);
    },
  };
}

export function useOperations() {
  return useQuery({
    queryKey: ["operations"],
    queryFn: async ({ signal }) =>
      requireData(await api.GET("/api/v1/operations", { signal })),
    staleTime: Infinity,
  });
}
export function useApplicableOperations(
  artifactId?: string,
  semanticRevisionId?: string | null,
) {
  return useQuery({
    queryKey: ["applicable-operations", artifactId, semanticRevisionId],
    enabled: !!artifactId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET(
          "/api/v1/representations/{artifact_id}/applicable-operations",
          {
            signal,
            params: {
              path: { artifact_id: artifactId! },
              query: semanticRevisionId
                ? { semantic_revision_id: semanticRevisionId }
                : {},
            },
          },
        ),
      ),
    staleTime: 15000,
  });
}
export function useProjectPlans(projectId: string) {
  return useQuery({
    queryKey: ["plans", projectId],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/projects/{project_id}/plans", {
          signal,
          params: {
            path: { project_id: projectId },
            query: { limit: 100, offset: 0 },
          },
        }),
      ),
  });
}
export function useCreatePlan(projectId: string) {
  const client = useQueryClient();
  const keys = useIdempotencyKeys();
  return useMutation({
    mutationFn: async (body: components["schemas"]["CreatePlanRequest"]) => {
      const signature = JSON.stringify(body);
      const result = requireData(
        await api.POST("/api/v1/projects/{project_id}/plans", {
          params: {
            path: { project_id: projectId },
            header: { "Idempotency-Key": keys.get(signature) },
          },
          body,
        }),
      );
      keys.done(signature);
      return result;
    },
    onSuccess: async (plan) => {
      client.setQueryData(["plan", plan.id], plan);
      await client.invalidateQueries({ queryKey: ["plans", projectId] });
    },
  });
}
export function useRevisePlan(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      familyId,
      body,
    }: {
      familyId: string;
      body: components["schemas"]["RevisePlanRequest"];
    }) =>
      requireData(
        await api.POST("/api/v1/plans/{family_id}/revisions", {
          params: { path: { family_id: familyId } },
          body,
        }),
      ),
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409)
        void client.invalidateQueries({ queryKey: ["plans", projectId] });
    },
    onSuccess: async (plan) => {
      client.setQueryData(["plan", plan.id], plan);
      await client.invalidateQueries({ queryKey: ["plans", projectId] });
    },
  });
}
export function useExecutePlan(versionId: string) {
  const client = useQueryClient();
  const keys = useIdempotencyKeys();
  return useMutation({
    mutationFn: async (revisionId: string) => {
      const result = requireData(
        await api.POST("/api/v1/plans/{revision_id}/executions", {
          params: {
            path: { revision_id: revisionId },
            header: { "Idempotency-Key": keys.get(revisionId) },
          },
        }),
      );
      keys.done(revisionId);
      return result;
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["executions", versionId] });
    },
  });
}

export function draftOf(plan?: Plan | null): PlanDraft {
  return {
    semantic_ref: plan?.semantic_ref ?? null,
    steps: plan?.steps ?? [],
  };
}
export function nextStepId(steps: PlanStep[], operation: string) {
  const base = (operation.split(".").pop() ?? "step").replace(
    /[^a-z0-9_]/g,
    "_",
  );
  let id = base;
  for (let i = 2; steps.some((step) => step.id === id); i++)
    id = `${base}_${i}`;
  return id;
}
