import { expect, test } from "@playwright/test";
import { csv, typedVersion } from "./analytics-support";

test("requisito semántico y «importe total por región y mes» con procedencia de cada cifra", async ({
  page,
}) => {
  // Incluye la preparación de v2 (limpieza y diagnóstico) por la API.
  test.setTimeout(120_000);
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Análisis",
      email: `analytics-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-12345",
    },
  });
  expect(registered.status()).toBe(201);
  await page.goto("/new");
  await page.getByLabel("Nombre del proyecto").fill("Análisis de ventas");
  await page.locator('input[type="file"]').setInputFiles({
    name: "ventas_calidad.csv",
    mimeType: "text/csv",
    buffer: csv,
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await expect(
    page.getByRole("heading", { name: "Vista previa del CSV", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  await typedVersion(page);
  await page.reload();
  const lineage = page.getByRole("status", {
    name: "Versión que estás viendo",
  });
  await expect(lineage).toContainText("Estás viendo v2", { timeout: 20000 });
  const stages = page.getByRole("navigation", { name: "Etapas del CSV real" });

  // 1. Métrica definida por el usuario: «Ingresos» = suma de importe por fecha de negocio.
  await stages.getByRole("button", { name: "Análisis", exact: false }).click();
  const stage = page.getByRole("region", { name: "Análisis de negocio" });
  await stage.getByRole("button", { name: "Nueva métrica" }).click();
  const dialog = page.getByRole("dialog", { name: "Nueva métrica" });
  await dialog.getByLabel("Nombre de negocio").fill("Ingresos");
  await dialog.getByLabel("Agregación").selectOption("sum");
  await dialog
    .getByLabel("Columna medida")
    .selectOption({ label: "importe · decimal" });
  await dialog.getByLabel("Fecha de negocio").selectOption({ label: "fecha" });
  await dialog.getByRole("button", { name: "Guardar métrica" }).click();
  await expect(dialog).toBeHidden();
  await expect(stage.getByLabel("Usar Ingresos")).toBeChecked();
  await stage.getByLabel("Agrupar por region", { exact: true }).check();
  await stage.getByLabel("Agrupar por tiempo").selectOption("month");
  await stage.getByRole("button", { name: "Calcular" }).click();

  // 2. Sin medida confirmada: requisito semántico pendiente con enlace a Entendimiento.
  const pending = stage.getByRole("alert", { name: "Requisitos pendientes" });
  await expect(pending).toContainText("Requisito semántico pendiente");
  await pending.getByRole("button", { name: "Ir a Entendimiento" }).click();

  // 3. Confirmar en Entendimiento: importe como medida en EUR y fecha como fecha de negocio.
  const editor = page.getByRole("region", {
    name: "Revisión semántica",
    exact: true,
  });
  await editor
    .getByLabel("Rol de importe", { exact: true })
    .selectOption("measure");
  await editor
    .getByRole("button", { name: "Detalles de importe", exact: true })
    .click();
  await page.getByRole("dialog").getByLabel("Moneda ISO 4217").fill("EUR");
  await page.getByRole("button", { name: "Aplicar al borrador" }).click();
  await editor
    .getByLabel("Revisión de importe", { exact: true })
    .selectOption("confirmed");
  await editor
    .getByLabel("Rol de fecha", { exact: true })
    .selectOption("business_date");
  await editor
    .getByLabel("Revisión de fecha", { exact: true })
    .selectOption("confirmed");
  await editor
    .getByRole("button", { name: "Guardar revisión semántica" })
    .click();
  await expect(
    editor.getByText("Revisión 1 guardada", { exact: true }),
  ).toBeVisible();

  // 4. Volver y ejecutar con la revisión fijada.
  await stages.getByRole("button", { name: "Análisis", exact: false }).click();
  await expect(stage.getByText("Revisión semántica 1")).toBeVisible();
  await stage.getByLabel("Usar Ingresos").check();
  await stage.getByLabel("Agrupar por region", { exact: true }).check();
  await stage.getByLabel("Agrupar por tiempo").selectOption("month");
  await stage.getByRole("button", { name: "Calcular" }).click();
  const results = stage.getByRole("table", { name: "Resultado del análisis" });
  await expect(results.locator("thead")).toContainText("Ingresos (EUR)", {
    timeout: 30000,
  });
  const rows = results.locator("tbody tr");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0)).toContainText("Este");
  await expect(rows.nth(0)).toContainText("120.25");
  await expect(rows.nth(1)).toContainText("Norte");
  await expect(rows.nth(1)).toContainText("2026-01");
  await expect(rows.nth(1)).toContainText("201.00");
  await expect(rows.nth(2)).toContainText("80.00");

  // 5. «De dónde sale este número».
  await rows.nth(1).getByRole("button").click();
  const provenance = page.getByRole("dialog", {
    name: "De dónde sale este número",
  });
  await expect(provenance.getByTestId("evidence-value")).toHaveText(
    "201.00 EUR",
  );
  await expect(provenance.getByTestId("evidence-counts")).toHaveText(
    "6 de entrada · 0 excluidas por filtros · 2 excluidas por nulos · 4 incluidas",
  );
  await expect(provenance).toContainText(
    "Ingresos · Suma de importe · revisión 1",
  );
  await expect(provenance).toContainText("Norte · 2026-01");
  await expect(provenance).toContainText("Revisión 1");
  await provenance
    .getByRole("button", { name: /cerrar/i })
    .first()
    .click();

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false);
});
