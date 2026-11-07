import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

export type PolicyContent = components["schemas"]["PolicyContent-Output"];
export type PolicyContentInput = components["schemas"]["PolicyContent-Input"];
export type PolicyRevision = components["schemas"]["PolicyRevision"];
export type PolicyDecision = components["schemas"]["PolicyDecision"];
export type Reason = components["schemas"]["Reason"];
export type CleaningOperation = NonNullable<
  PolicyContent["allowed_operations"]
>[number];

export function useAutomationPolicy(projectId: string) {
  return useQuery({
    queryKey: ["automation-policy", projectId],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/projects/{project_id}/automation-policy", {
          signal,
          params: { path: { project_id: projectId } },
        }),
      ).revision,
  });
}

/** Guarda una revisión nueva de la política (`expected_revision`, `Idempotency-Key`). */
export function useSavePolicy(projectId: string) {
  const client = useQueryClient();
  const keys = useRef(new Map<string, string>());
  return useMutation({
    mutationFn: async ({
      expected,
      content,
    }: {
      expected: number;
      content: PolicyContentInput;
    }) => {
      const signature = JSON.stringify({ expected, content });
      let key = keys.current.get(signature);
      if (!key) {
        key = crypto.randomUUID();
        keys.current.set(signature, key);
      }
      return requireData(
        await api.POST("/api/v1/projects/{project_id}/automation-policy", {
          params: {
            path: { project_id: projectId },
            header: { "Idempotency-Key": key },
          },
          body: { expected_revision: expected, content },
        }),
      );
    },
    onSuccess: (revision) => {
      client.setQueryData(["automation-policy", projectId], revision);
      // Una revisión nueva revoca las aprobaciones automáticas aún no aplicadas.
      void client.invalidateQueries({ queryKey: ["cleaning-preview"] });
    },
  });
}

export function useApproveByPolicy(executionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      requireData(
        await api.POST("/api/v1/previews/{execution_id}/policy-approvals", {
          params: { path: { execution_id: executionId } },
        }),
      ),
    onSuccess: () =>
      client.invalidateQueries({
        queryKey: ["cleaning-preview", executionId],
      }),
  });
}

export function useApprovalOrigin(approvalId: string | null) {
  return useQuery({
    queryKey: ["approval-origin", approvalId],
    enabled: !!approvalId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/approvals/{approval_id}/origin", {
          signal,
          params: { path: { approval_id: approvalId! } },
        }),
      ),
  });
}

export type AutomationRun = components["schemas"]["AutomationRunView"];

const active = (run?: AutomationRun | null) => run?.state === "running";

/** Pipeline automático de una versión (Fase 11C); se consulta mientras está en curso. */
export function useVersionRun(versionId: string) {
  return useQuery({
    queryKey: ["automation-run", versionId],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/versions/{version_id}/automation-run", {
          signal,
          params: { path: { version_id: versionId } },
        }),
      ).run,
    refetchInterval: (query) => (active(query.state.data) ? 2000 : false),
  });
}

/** Pipelines que necesitan a una persona (`needs_review` o `failed`). */
export function useNotifications() {
  return useQuery({
    queryKey: ["automation-notifications"],
    queryFn: async ({ signal }) =>
      requireData(await api.GET("/api/v1/notifications", { signal })).items,
    refetchInterval: 15000,
  });
}

export function useCancelRun(versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (runId: string) =>
      requireData(
        await api.POST("/api/v1/automation-runs/{run_id}/cancel", {
          params: { path: { run_id: runId } },
        }),
      ),
    onSuccess: (run) => client.setQueryData(["automation-run", versionId], run),
  });
}
