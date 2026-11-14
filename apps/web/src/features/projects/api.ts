import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@dataflow/api-client";
import { api, requireData } from "@/lib/api";
import type { Project } from "@/lib/project";

export type ApiProject = components["schemas"]["ProjectResponse"];
export function projectView(p: ApiProject): Project {
  return {
    id: p.id,
    name: p.name,
    description: p.description,
    file: p.file_name ?? "Sin dataset",
    status: p.status,
    updated: p.updated_at,
    rows: 0,
    columns: 0,
  };
}
export function useProjects(
  q = "",
  status?: "draft" | "archived",
  limit = 20,
  offset = 0,
  enabled = true,
) {
  return useQuery({
    queryKey: ["projects", { q, status, limit, offset }],
    enabled,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/projects", {
          signal,
          params: { query: { q, status, limit, offset } },
        }),
      ),
    staleTime: 15000,
  });
}
export function useProject(id: string, enabled = true) {
  return useQuery({
    queryKey: ["project", id],
    enabled,
    queryFn: async ({ signal }) =>
      requireData(
        await api.GET("/api/v1/projects/{project_id}", {
          signal,
          params: { path: { project_id: id } },
        }),
      ),
    retry: false,
  });
}
export function useCreateProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: components["schemas"]["CreateProjectRequest"]) =>
      requireData(await api.POST("/api/v1/projects", { body })),
    onSuccess: async (p) => {
      client.setQueryData(["project", p.id], p);
      await client.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
export function useUpdateProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      body,
    }: {
      id: string;
      body: components["schemas"]["UpdateProjectRequest"];
    }) =>
      requireData(
        await api.PATCH("/api/v1/projects/{project_id}", {
          params: { path: { project_id: id } },
          body,
        }),
      ),
    onSuccess: async (p) => {
      client.setQueryData(["project", p.id], p);
      await client.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
export function useArchiveProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (p: ApiProject) =>
      requireData(
        await api.POST("/api/v1/projects/{project_id}/archive", {
          params: { path: { project_id: p.id } },
          body: { expected_revision: p.revision },
        }),
      ),
    onSuccess: async (p) => {
      client.setQueryData(["project", p.id], p);
      await client.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
