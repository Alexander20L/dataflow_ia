import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";

type Schemas = components["schemas"];
export type DashboardView = Schemas["DashboardView"];
export type DashboardRevision = Schemas["DashboardRevision"];
export type DashboardDraft = Schemas["DashboardDraft"];
export type Card = Schemas["Card"];
export type CardState = Schemas["CardState"];
export type GlobalFilter = Schemas["GlobalFilter"];
export type CardView = Card["view"];
export type CardSize = NonNullable<Card["size"]>;

/** Clave idempotente estable por contenido: un reintento reutiliza la misma solicitud. */
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

export function useDashboards(projectId: string) {
  return useQuery({
    queryKey: ["dashboards", projectId],
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/projects/{project_id}/dashboards", {
          signal,
          params: { path: { project_id: projectId } },
        }),
      ),
  });
}

export function useDashboard(familyId: string | null) {
  return useQuery({
    queryKey: ["dashboard", familyId],
    enabled: !!familyId,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/dashboards/{family_id}", {
          signal,
          params: { path: { family_id: familyId! } },
        }),
      ),
    // Mientras alguna tarjeta se calcula, se consulta de nuevo.
    refetchInterval: (query) =>
      query.state.data?.cards.some((c) => c.status === "pending")
        ? 1500
        : false,
  });
}

function useInvalidate() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: ["dashboards"] });
    void client.invalidateQueries({ queryKey: ["dashboard"] });
  };
}

export function useCreateDashboard(projectId: string) {
  const keys = useKeys();
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (draft: DashboardDraft) => {
      const body = { draft };
      const { key, done } = keys.get(body);
      const result = requireData(
        await api.POST("/api/v1/projects/{project_id}/dashboards", {
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

export function useReviseDashboard() {
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
      draft: DashboardDraft;
    }) => {
      const body = { expected_revision: expected, draft };
      const { key, done } = keys.get({ familyId, ...body });
      const result = requireData(
        await api.POST("/api/v1/dashboards/{family_id}/revisions", {
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

export function useRefreshDashboard() {
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
        await api.POST("/api/v1/dashboards/{family_id}/refresh", {
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

/** Borrador editable a partir de una revisión guardada. */
export function draftOf(revision: DashboardRevision): DashboardDraft {
  const { title, description, cards, filters } = revision.content;
  return { title, description, cards: cards ?? [], filters: filters ?? [] };
}

/** Tipos de tarjeta posibles según la forma de la consulta (mismas reglas que el servidor). */
export function allowedViews(dimensions: number, grain: boolean): CardView[] {
  const views: CardView[] = [];
  if (!dimensions && !grain) views.push("kpi");
  if (grain) views.push("line");
  if (dimensions + (grain ? 1 : 0) === 1) views.push("bar");
  views.push("table");
  return views;
}

export const VIEW_LABELS: Record<CardView, string> = {
  kpi: "KPI",
  table: "Tabla",
  bar: "Barras",
  line: "Líneas",
};

export const SIZE_LABELS: Record<CardSize, string> = {
  small: "Pequeña",
  medium: "Mediana",
  large: "Grande",
};
