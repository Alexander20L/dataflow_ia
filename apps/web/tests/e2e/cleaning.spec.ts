import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const csv = readFileSync(
  path.resolve(__dirname, "../../../../examples/ventas_calidad.csv"),
);

async function state(page: Page, run: string) {
  return (await (await page.request.get(`/api/v1/executions/${run}`)).json())
    .state;
}

test("limpiar espacios en una columna: vista previa, aprobación y versión derivada con v1 intacta", async ({
  page,
}) => {
  // Vista previa, aplicación y diagnóstico de v2 en el worker: ~30 s en un equipo cargado.
  test.setTimeout(60_000);
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Limpieza",
      email: `cleaning-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-12345",
    },
  });
  expect(registered.status()).toBe(201);
  await page.goto("/new");
  await page.getByLabel("Nombre del proyecto").fill("Limpieza de ventas");
  await page.locator('input[type="file"]').setInputFiles({
    name: "ventas_calidad.csv",
    mimeType: "text/csv",
    buffer: csv,
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await expect(
    page.getByRole("heading", { name: "Vista previa del CSV", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  const versionSelect = page.getByLabel("Versión", { exact: true });
  const v1 = await versionSelect.inputValue();
  // Métrica principal del diagnóstico de la versión seleccionada.
  const completeness = page
    .locator(".mini-metrics > div")
    .filter({ hasText: "Completitud de celdas" });
  const lineage = page.getByRole("status", {
    name: "Versión que estás viendo",
  });
  await expect(lineage).toContainText("Estás viendo v1, importada");

  // 1. Propuesta desde el diagnóstico: Q-003 sugiere recortar «importe».
  await page
    .getByRole("navigation", { name: "Etapas del CSV real" })
    .getByRole("button", { name: "Limpieza", exact: false })
    .click();
  const stage = page.getByRole("region", { name: "Limpieza supervisada" });
  const trim = stage.getByLabel("Recortar importe", { exact: true });
  await expect(trim).toBeChecked();
  // Q-001 también sugiere excluir nulos; este recorrido sólo recorta.
  await stage.getByLabel("Excluir nulos de importe", { exact: true }).uncheck();
  // El borrador editado no está guardado: salir de la etapa pide confirmación.
  await expect(stage.getByText("Cambios sin guardar")).toBeVisible();
  await page
    .getByRole("navigation", { name: "Etapas del CSV real" })
    .getByRole("button", { name: "Calidad", exact: false })
    .click();
  const unsaved = page.getByRole("dialog", {
    name: "Hay cambios sin guardar en la propuesta de limpieza",
  });
  await unsaved.getByRole("button", { name: "Seguir editando" }).click();
  await expect(unsaved).toBeHidden();
  await expect(
    stage.getByLabel("Excluir nulos de importe", { exact: true }),
  ).not.toBeChecked();
  // Q-002 sugiere deduplicar (Fase 6); este recorrido sólo recorta.
  await stage
    .getByLabel("Eliminar registros duplicados", { exact: true })
    .uncheck();
  await stage
    .getByRole("button", { name: "Generar vista previa", exact: true })
    .click();

  // 2. Vista previa sobre todo el dataset: 1 nulo creado, destacado.
  const effect = stage.getByRole("region", { name: "Vista previa del efecto" });
  await expect(effect.getByTestId("created-nulls")).toHaveText("1", {
    timeout: 20000,
  });
  await expect(
    effect.getByText("La completitud de la nueva versión puede bajar", {
      exact: false,
    }),
  ).toBeVisible();
  const samples = effect.getByRole("table", {
    name: "Ejemplos antes y después",
  });
  await expect(samples).toContainText("importe");
  await expect(samples).toContainText("Nulo creado");

  // 3. Aprobar el efecto exacto y aplicar.
  await effect.getByRole("button", { name: "Aprobar efecto…" }).click();
  const dialog = page.getByRole("dialog", {
    name: "Aprobar el efecto de la limpieza",
  });
  await expect(dialog).toContainText("1 nulo(s) creado(s)");
  await dialog.getByRole("button", { name: "Aprobar este efecto" }).click();
  await effect.getByRole("button", { name: "Aplicar limpieza" }).click();
  await expect(effect.getByText("Versión derivada creada")).toBeVisible({
    timeout: 30000,
  });
  await effect.getByRole("button", { name: "Ver la versión derivada" }).click();

  // 4. v2 derivada con diagnóstico nuevo; se indica su origen.
  await expect(versionSelect).not.toHaveValue(v1);
  const v2 = await versionSelect.inputValue();
  await expect(lineage).toContainText("Estás viendo v2");
  await expect(lineage).toContainText("derivada");
  await expect(lineage).toContainText("v1");
  await expect(completeness.getByText("93,33 %", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await expect(
    page.getByRole("link", { name: "Descargar original de v1" }),
  ).toHaveAttribute("href", `/api/v1/versions/${v1}/original`);
  const versions = await (
    await page.request.get(
      `/api/v1/projects/${(await (await page.request.get("/api/v1/projects")).json()).items[0].id}/versions`,
    )
  ).json();
  const derived = versions.items.find((v: { id: string }) => v.id === v2);
  expect(derived.kind).toBe("derived");
  expect(derived.parent_version_id).toBe(v1);
  const lineageResponse = await (
    await page.request.get(`/api/v1/versions/${v2}/lineage`)
  ).json();
  expect(lineageResponse.operations[0].operation).toBe(
    "cleaning.trim_whitespace",
  );
  await expect
    .poll(() => state(page, lineageResponse.producer_execution_id))
    .toBe("succeeded");

  // 5. v1 sigue seleccionable e intacta.
  await lineage.getByRole("button", { name: "Ver v1" }).click();
  await expect(versionSelect).toHaveValue(v1);
  await expect(
    completeness.getByText("96,67 %", { exact: true }),
  ).toBeVisible();
  const v1Diagnostic = await (
    await page.request.get(`/api/v1/versions/${v1}/diagnostic`)
  ).json();
  expect(v1Diagnostic.quality.completeness_percent).toBe(96.67);
  expect(
    await (await page.request.get(`/api/v1/versions/${v1}/original`)).body(),
  ).toEqual(csv);
  const blocked = await page.request.get(`/api/v1/versions/${v2}/original`);
  expect(blocked.status()).toBe(409);

  // 6. Con más de 20 versiones el origen puede estar en otra página del selector: se simula
  // quitando v1 del listado (total 21) y «Ver v1» la carga por ID con la API real.
  const listing = /\/api\/v1\/projects\/[^/]+\/versions(\?|$)/;
  await page.route(listing, async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.items = body.items.filter((v: { id: string }) => v.id !== v1);
    body.total = 21;
    await route.fulfill({ response, json: body });
  });
  await page.reload();
  await expect(lineage).toContainText("Estás viendo v2", { timeout: 20000 });
  await expect(versionSelect.locator(`option[value="${v1}"]`)).toHaveCount(0);
  await lineage.getByRole("button", { name: "Ver v1" }).click();
  await expect(versionSelect).toHaveValue(v1);
  await expect(versionSelect.locator("option:checked")).toContainText(
    "fuera de esta página",
  );
  await expect(lineage).toContainText("Estás viendo v1, importada");
  await expect(completeness.getByText("96,67 %", { exact: true })).toBeVisible({
    timeout: 20000,
  });
  await page.unroute(listing);

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false);
});
