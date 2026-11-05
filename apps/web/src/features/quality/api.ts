import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";
import type { Execution } from "@/features/executions/api";

export type RulesetContext = components["schemas"]["RulesetContext"];
export type RulesetRevision = components["schemas"]["RulesetRevision"];
export type RulesetDraft = components["schemas"]["RulesetDraft"];
export type Rule = RulesetDraft["rules"] extends (infer R)[] | undefined
  ? R
  : never;
export type QualityRulesReport = components["schemas"]["QualityRulesReport"];

/** ¿El plan de la ejecución contiene esta operación? (decide qué resultados consultar). */
export function runHasStep(run: Execution | undefined, key: string) {
  const content = run?.plan?.content as
    { steps?: { operation: string; version: number }[] } | undefined;
  return (content?.steps ?? []).some(
    (step) => `${step.operation}@${step.version}` === key,
  );
}

export function useQualityRulesets(artifactId?: string) {
  return useQuery({
    queryKey: ["quality-rulesets", artifactId],
    enabled: !!artifactId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET(
          "/api/v1/representations/{artifact_id}/quality-rulesets",
          {
            signal,
            params: { path: { artifact_id: artifactId! } },
          },
        ),
      ),
  });
}

export function useSaveRuleset(artifactId: string) {
  const client = useQueryClient();
  const keys = useRef(new Map<string, string>());
  return useMutation({
    mutationFn: async (body: components["schemas"]["SaveRulesetRequest"]) => {
      const signature = JSON.stringify(body);
      let key = keys.current.get(signature);
      if (!key) {
        key = crypto.randomUUID();
        keys.current.set(signature, key);
      }
      const result = requireData(
        await api.POST(
          "/api/v1/representations/{artifact_id}/quality-rulesets",
          {
            params: {
              path: { artifact_id: artifactId },
              header: { "Idempotency-Key": key },
            },
            body,
          },
        ),
      );
      keys.current.delete(signature);
      return result;
    },
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["quality-rulesets"] }),
  });
}

export function useQualityRulesReport(run?: Execution, enabled = true) {
  return useQuery({
    queryKey: ["quality-rules-report", run?.id],
    enabled: enabled && run?.state === "succeeded",
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/executions/{execution_id}/quality-rules", {
          signal,
          params: { path: { execution_id: run!.id } },
        }),
      ),
    staleTime: Infinity,
  });
}

export function useRun(runId: string | null) {
  return useQuery({
    queryKey: ["quality-rules-run", runId],
    enabled: !!runId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/executions/{execution_id}", {
          signal,
          params: { path: { execution_id: runId! } },
        }),
      ),
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.state ?? "queued")
        ? 1000
        : false,
  });
}
