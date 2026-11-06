/** Apoyo de las pruebas E2E de análisis: preparación por la API (fuera de lo que se prueba). */
import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const csv = readFileSync(
  path.resolve(__dirname, "../../../../examples/ventas_calidad.csv"),
);

export async function mutate(
  request: APIRequestContext,
  url: string,
  data?: unknown,
): Promise<Record<string, unknown>> {
  const session = await (await request.get("/api/v1/auth/me")).json();
  const response = await request.post(url, {
    headers: {
      Origin: "http://127.0.0.1:3100",
      "x-csrf-token": session.csrf_token,
      "Idempotency-Key": crypto.randomUUID(),
    },
    data,
  });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

/** v2 tipada (importe decimal(2), fecha ISO) mediante el ciclo supervisado de limpieza. */
export async function typedVersion(page: Page) {
  const request = page.request;
  const project = (await (await request.get("/api/v1/projects")).json())
    .items[0];
  const versions = await (
    await request.get(`/api/v1/projects/${project.id}/versions`)
  ).json();
  const table = (
    await (
      await request.get(
        `/api/v1/versions/${versions.items[0].id}/representations`,
      )
    ).json()
  )[0];
  const id = (name: string) =>
    table.columns.find((c: { name: string }) => c.name === name).id;
  const plan = await mutate(request, `/api/v1/projects/${project.id}/plans`, {
    table_artifact_id: table.id,
    table_sha256: table.sha256,
    semantic_ref: null,
    steps: [
      {
        id: "trim",
        operation: "cleaning.trim_whitespace",
        version: 1,
        input: { kind: "input", alias: "source" },
        parameters: { column_ids: [id("importe")] },
      },
      {
        id: "importe",
        operation: "cleaning.cast",
        version: 1,
        input: { kind: "step", step_id: "trim" },
        parameters: {
          column_id: id("importe"),
          type: "decimal",
          format: "decimal_dot",
          scale: 2,
        },
      },
      {
        id: "fecha",
        operation: "cleaning.cast",
        version: 1,
        input: { kind: "step", step_id: "importe" },
        parameters: {
          column_id: id("fecha"),
          type: "date",
          format: "iso_date",
        },
      },
    ],
  });
  const preview = await mutate(request, `/api/v1/plans/${plan.id}/previews`);
  let view: Record<string, unknown> = {};
  await expect
    .poll(
      async () => {
        view = await (
          await request.get(`/api/v1/previews/${preview.id}`)
        ).json();
        return view.state;
      },
      { timeout: 30000 },
    )
    .toBe("succeeded");
  const approval = await mutate(
    request,
    `/api/v1/previews/${preview.id}/approvals`,
    { effect_sha256: view.effect_sha256 },
  );
  await mutate(request, `/api/v1/approvals/${approval.id}/apply`);
  await expect
    .poll(
      async () => {
        const list = await (
          await request.get(`/api/v1/projects/${project.id}/versions`)
        ).json();
        return list.items.map((v: { state: string }) => v.state).join(",");
      },
      { timeout: 40000 },
    )
    .toBe("succeeded,succeeded");
}

/** Tabla publicada de la versión más reciente (la v2 tipada) y el ID de cada columna. */
export async function latestTable(request: APIRequestContext) {
  const project = (await (await request.get("/api/v1/projects")).json())
    .items[0];
  const versions = await (
    await request.get(`/api/v1/projects/${project.id}/versions`)
  ).json();
  const table = (
    await (
      await request.get(
        `/api/v1/versions/${versions.items[0].id}/representations`,
      )
    ).json()
  )[0];
  const id = (name: string): string =>
    table.columns.find((c: { name: string }) => c.name === name).id;
  return { table, id };
}

/** Revisión semántica confirmada: importe como medida en EUR y fecha como fecha de negocio. */
export async function confirmSemantics(request: APIRequestContext) {
  const { table, id } = await latestTable(request);
  const context = await (
    await request.get(`/api/v1/representations/${table.id}/understanding`)
  ).json();
  const draft = context.editable;
  for (const column of draft.columns) {
    if (column.column_id === id("importe"))
      Object.assign(column, {
        role: "measure",
        currency: "EUR",
        review_state: "confirmed",
      });
    if (column.column_id === id("fecha"))
      Object.assign(column, {
        role: "business_date",
        review_state: "confirmed",
      });
  }
  await mutate(
    request,
    `/api/v1/representations/${table.id}/semantic-contracts`,
    {
      table_sha256: table.sha256,
      expected_revision: context.revision_count,
      draft,
    },
  );
}

/** Métrica guardada sobre la v2 con «fecha» como fecha de negocio (`measure`: nombre de columna). */
export async function saveMetric(
  request: APIRequestContext,
  label: string,
  aggregation: string,
  measure: string,
) {
  const { table, id } = await latestTable(request);
  await mutate(request, `/api/v1/representations/${table.id}/metrics`, {
    table_sha256: table.sha256,
    family_id: null,
    expected_revision: 0,
    draft: {
      label,
      aggregation,
      measure_column_id: id(measure),
      time_column_id: id("fecha"),
      filters: [],
      null_policy: "exclude",
    },
  });
}
