import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { openAdvanced } from "./workspace-support";
import {
  confirmSemantics,
  csv,
  saveMetric,
  typedVersion,
} from "./analytics-support";

test("informe de un CSV propio exportado a PDF y CSV de una versión derivada", async ({
  page,
}) => {
  // Preparación de v2, semántica y métrica por la API; un análisis, el informe y el PDF.
  test.setTimeout(180_000);
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Informes",
      email: `reports-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-12345",
    },
  });
  expect(registered.status()).toBe(201);
  await page.goto("/new");
  await page.getByLabel("Nombre del proyecto").fill("Informes de ventas");
  await page.locator('input[type="file"]').setInputFiles({
    name: "ventas_calidad.csv",
    mimeType: "text/csv",
    buffer: csv,
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await openAdvanced(page);
  await expect(
    page.getByRole("heading", { name: "Vista previa del CSV", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  await typedVersion(page);
  await confirmSemantics(page.request);
  await saveMetric(page.request, "Ingresos", "sum", "importe");
  await page.reload();
  await openAdvanced(page);
  await expect(
    page.getByRole("status", { name: "Versión que estás viendo" }),
  ).toContainText("Estás viendo v2", { timeout: 20000 });
  const stages = page.getByRole("navigation", { name: "Etapas del CSV real" });

  // 1. CSV de la versión derivada (antes 409 en /original), en ambos perfiles.
  const [standard] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Exportar v2" }).click(),
  ]);
  expect(standard.suggestedFilename()).toMatch(/-v2\.csv$/);
  const standardText = await readFile((await standard.path())!, "utf-8");
  expect(standardText.split("\n")[0]).toBe("id,fecha,region,importe,unidades");
  expect(standardText).toContain("001,2026-01-01,Norte,100.50,2");
  await page.getByLabel("Perfil de Exportar v2").selectOption("excel_regional");
  const [regional] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Exportar v2" }).click(),
  ]);
  const regionalBytes = await readFile((await regional.path())!);
  expect([...regionalBytes.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
  expect(regionalBytes.toString("utf-8")).toContain(
    "001;2026-01-01;Norte;100,50;2\r\n",
  );

  // 2. Un análisis calculado: ingresos por región.
  await stages.getByRole("button", { name: "Análisis", exact: false }).click();
  const analysis = page.getByRole("region", { name: "Análisis de negocio" });
  await analysis.getByLabel("Usar Ingresos").check();
  await analysis.getByLabel("Agrupar por region", { exact: true }).check();
  await analysis.getByRole("button", { name: "Calcular" }).click();
  await expect(
    analysis.getByRole("table", { name: "Resultado del análisis" }),
  ).toBeVisible({ timeout: 30000 });

  // 3. Informe con texto, resultado exacto, conclusión y limitaciones.
  await stages.getByRole("button", { name: "Explicación" }).click();
  const reports = page.getByRole("region", { name: "Informes" });
  await reports.getByRole("button", { name: "Nuevo informe" }).click();
  const create = page.getByRole("dialog", { name: "Nuevo informe" });
  await create.getByLabel("Nombre del informe").fill("Informe de ventas");
  await create.getByRole("button", { name: "Crear informe" }).click();
  await expect(create).toBeHidden();
  await reports.getByRole("button", { name: "Texto", exact: true }).click();
  await reports.getByLabel("Texto 1").fill("Resumen de ventas de enero.");
  await reports.getByRole("button", { name: "Resultado de análisis" }).click();
  const add = page.getByRole("dialog", {
    name: "Añadir resultado de análisis",
  });
  await add.getByLabel("Ejecución del análisis").selectOption({ index: 1 });
  await add.getByLabel("Título del bloque").fill("Ingresos por región");
  await add.getByRole("button", { name: "Añadir bloque" }).click();
  await reports.getByRole("button", { name: "Conclusión" }).click();
  await reports.getByLabel("Conclusión 3").fill("Norte lidera los ingresos.");
  await reports.getByRole("button", { name: "Limitaciones" }).click();
  await reports
    .getByLabel("Limitaciones 4")
    .fill("Sur tiene importes nulos, que no cuentan como cero.");
  await reports.getByRole("button", { name: "Guardar revisión" }).click();
  await expect(
    reports.getByLabel("Revisión del informe").locator("option").first(),
  ).toHaveText(/revisión 2/);

  // Procedencia automática del bloque de datos y cifras con evidencia.
  const provenance = reports.getByTestId("block-provenance");
  await expect(provenance).toContainText("ventas_calidad.csv · limpieza · v2");
  await expect(provenance).toContainText("filtros: ninguno");
  const block = reports.locator("li.report-block.kind-analysis");
  await expect(block.getByRole("table")).toContainText("201.00");

  // 4. PDF generado por el worker a partir de la revisión exacta, descargado.
  await reports
    .getByRole("button", { name: "Exportar PDF (revisión 2)" })
    .click();
  const link = reports.getByRole("link", {
    name: "Descargar PDF (revisión 2)",
  });
  await expect(link).toBeVisible({ timeout: 30000 });
  const [pdf] = await Promise.all([
    page.waitForEvent("download"),
    link.click(),
  ]);
  expect(pdf.suggestedFilename()).toMatch(/^informe-r2-.*\.pdf$/);
  const bytes = await readFile((await pdf.path())!);
  expect(bytes.subarray(0, 5).toString("latin1")).toBe("%PDF-");
  expect(bytes.length).toBeGreaterThan(1000);

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false);
});
