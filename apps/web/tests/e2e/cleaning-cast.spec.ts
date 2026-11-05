import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const csv = readFileSync(
  path.resolve(__dirname, "../../../../examples/ventas_calidad.csv"),
);

async function prepare(page: Page, name: string) {
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name,
      email: `cast-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-12345",
    },
  });
  expect(registered.status()).toBe(201);
  await page.goto("/new");
  await page.getByLabel("Nombre del proyecto").fill(name);
  await page.locator('input[type="file"]').setInputFiles({
    name: "ventas_calidad.csv",
    mimeType: "text/csv",
    buffer: csv,
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await expect(
    page.getByRole("heading", { name: "Vista previa del CSV", exact: true }),
  ).toBeVisible({ timeout: 20000 });
}

async function openStage(page: Page, name: string) {
  await page
    .getByRole("navigation", { name: "Etapas del CSV real" })
    .getByRole("button", { name, exact: false })
    .click();
}

async function versionCount(page: Page) {
  const projects = await (await page.request.get("/api/v1/projects")).json();
  const versions = await (
    await page.request.get(`/api/v1/projects/${projects.items[0].id}/versions`)
  ).json();
  return versions.total as number;
}

test("una conversión con valores inválidos bloquea la publicación; corregida crea v2 tipada", async ({
  page,
}) => {
  await prepare(page, "Conversión de importes");
  await openStage(page, "Limpieza");
  const stage = page.getByRole("region", { name: "Limpieza supervisada" });
  // Sólo convertir «importe»: sin recortar, la celda de espacios (registro 5) no convierte.
  await stage.getByLabel("Recortar importe", { exact: true }).uncheck();
  await stage.getByLabel("Excluir nulos de importe", { exact: true }).uncheck();
  await stage
    .getByLabel("Eliminar registros duplicados", { exact: true })
    .uncheck();
  await stage
    .getByLabel("Convertir importe", { exact: true })
    .selectOption("decimal");
  await expect(
    stage.getByLabel("Escala de importe", { exact: true }),
  ).toHaveValue("2");
  await stage
    .getByRole("button", { name: "Generar vista previa", exact: true })
    .click();

  const failure = stage.getByRole("region", {
    name: "Valores que impiden la limpieza",
  });
  await expect(failure).toContainText("1 valor(es) no se pueden convertir", {
    timeout: 20000,
  });
  const rows = failure.getByRole("table", {
    name: "Valores que no convierten",
  });
  await expect(rows.locator("tbody tr")).toHaveCount(1);
  await expect(rows.locator("tbody tr").first()).toContainText("importe");
  await expect(rows.locator("tbody tr").first()).toContainText("5");
  await expect(rows.locator("tbody tr").first()).toContainText(
    "Espacios en los bordes",
  );
  await expect(failure.getByTestId("failure-total")).toContainText(
    "Se muestran 1 de 1",
  );
  // Nada aprobable ni publicado.
  await expect(
    stage.getByRole("button", { name: "Aprobar efecto…" }),
  ).toHaveCount(0);
  expect(await versionCount(page)).toBe(1);

  // Corregir el plan: recortar antes de convertir.
  await stage.getByRole("button", { name: "Editar propuesta" }).click();
  await stage.getByLabel("Recortar importe", { exact: true }).check();
  await stage
    .getByRole("button", { name: "Generar vista previa", exact: true })
    .click();
  const effect = stage.getByRole("region", { name: "Vista previa del efecto" });
  await expect(effect.getByTestId("output-types")).toContainText(
    "importe → decimal (2 decimales)",
    { timeout: 20000 },
  );
  await expect(effect.getByTestId("rounded-cells")).toHaveText("0");
  await expect(effect.getByTestId("created-nulls")).toHaveText("1");
  await effect.getByRole("button", { name: "Aprobar efecto…" }).click();
  await page
    .getByRole("dialog", { name: "Aprobar el efecto de la limpieza" })
    .getByRole("button", { name: "Aprobar este efecto" })
    .click();
  await effect.getByRole("button", { name: "Aplicar limpieza" }).click();
  await expect(effect.getByText("Versión derivada creada")).toBeVisible({
    timeout: 30000,
  });
  await effect.getByRole("button", { name: "Ver la versión derivada" }).click();
  const lineage = page.getByRole("status", {
    name: "Versión que estás viendo",
  });
  await expect(lineage).toContainText("Estás viendo v2");
  expect(await versionCount(page)).toBe(2);

  // La derivada tiene «importe» decimal: su perfil lo muestra y ya no es texto.
  await openStage(page, "Entendimiento");
  const row = page.locator("tr").filter({ hasText: "importe" }).first();
  await expect(row.locator("td.mono")).toHaveText("decimal", {
    timeout: 30000,
  });
  await expect(
    page.getByText("columnas convertidas por una limpieza aprobada", {
      exact: false,
    }),
  ).toBeVisible();
});

test("requisito semántico: un identificador confirmado exige confirmar su conversión y «001» no se convierte", async ({
  page,
}) => {
  await prepare(page, "Identificadores");
  // 1. Entendimiento: «id» confirmado como identificador.
  await openStage(page, "Entendimiento");
  const editor = page.getByRole("region", {
    name: "Revisión semántica",
    exact: true,
  });
  await editor
    .getByLabel("Rol de id", { exact: true })
    .selectOption("identifier");
  await editor
    .getByLabel("Revisión de id", { exact: true })
    .selectOption("confirmed");
  await editor
    .getByRole("button", { name: "Guardar revisión semántica" })
    .click();
  await expect(
    editor.getByText("Revisión 1 guardada", { exact: true }),
  ).toBeVisible();

  // 2. Limpieza: la propuesta fija esa revisión y la conversión numérica pide confirmación.
  await openStage(page, "Limpieza");
  const stage = page.getByRole("region", { name: "Limpieza supervisada" });
  await expect(stage.getByTestId("semantic-pin")).toContainText(
    "revisión semántica 1",
  );
  for (const label of ["Recortar importe", "Excluir nulos de importe"])
    await stage.getByLabel(label, { exact: true }).uncheck();
  await stage
    .getByLabel("Eliminar registros duplicados", { exact: true })
    .uncheck();
  await stage
    .getByLabel("Convertir id", { exact: true })
    .selectOption("integer");
  const generate = stage.getByRole("button", {
    name: "Generar vista previa",
    exact: true,
  });
  await expect(
    stage.getByText("la revisión semántica la marca como identificador", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(generate).toBeDisabled();
  await stage
    .getByLabel("Confirmo convertir el identificador id a número", {
      exact: true,
    })
    .check();
  await expect(generate).toBeEnabled();
  await generate.click();

  // 3. Segunda línea de defensa: «001» tiene ceros a la izquierda y no es un entero canónico.
  const failure = stage.getByRole("region", {
    name: "Valores que impiden la limpieza",
  });
  await expect(failure).toContainText("6 valor(es) no se pueden convertir", {
    timeout: 20000,
  });
  await expect(
    failure.getByRole("table", { name: "Valores que no convierten" }),
  ).toContainText("Ceros a la izquierda");
  expect(await versionCount(page)).toBe(1);
});
