import { readFile } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { openFindings, openTab } from "./helpers";

// Fase 14: dataset sintético de aceptación (Year + Month, Customer con dos nombres, un mes
// faltante y sin moneda). Cero clics después de subir.
test("análisis con criterio: periodo mensual, medidas y clientes limitados", async ({
  page,
}) => {
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista Fase 14",
      email: `fase14-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-Fase14-123",
    },
  });
  expect(registration.status()).toBe(201);
  const csv = await readFile(
    path.join(__dirname, "fixtures", "ventas_mensuales.csv"),
  );
  await page.goto("/new");
  await page.locator('input[type="file"]').setInputFiles({
    name: "ventas_mensuales.csv",
    mimeType: "text/csv",
    buffer: csv,
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  // Fase 28: el progreso de la carga va encima de las pestañas.
  const stages = page.getByRole("list", { name: "Progreso de la carga" });
  await expect(stages.getByRole("listitem")).toHaveCount(5, { timeout: 30000 });
  // Fase 15 (Fase 28: en Investigación): los hallazgos aparecen sin ninguna acción.
  const findings = await openFindings(page);
  await expect(
    findings.getByRole("heading", { name: "Hallazgos" }),
  ).toBeVisible();
  await expect(findings).toContainText(
    "En los 11 meses de 2024 con dato también en 2023",
  );
  await expect(
    findings.getByRole("article", { name: "Mes atípico de Revenue: 2024-10" }),
  ).toContainText("Se asocia sobre todo a Product = Monitor");
  await expect(findings).toContainText(
    "Laptop concentra el 62,00 % de Revenue",
  );
  await findings.getByText(/Análisis omitidos/).click();
  await expect(findings).toContainText("Hacen falta 24 meses seguidos");
  await expect(findings.getByRole("button")).toHaveCount(0);
  // Fase 27: el seguimiento de hallazgos de la Fase 16 ya no se ejecuta en las cargas nuevas.
  await expect(
    page.getByRole("tab", { name: "Seguimiento anterior" }),
  ).toHaveCount(0);
  // Fase 28: no queda la pestaña Análisis.
  await expect(
    page.getByRole("tab", { name: "Análisis", exact: true }),
  ).toHaveCount(0);
  // Fase 19 y 24: la comprensión (IA falsa) vive en su propia pestaña; rechazar una relación.
  await page.getByRole("tab", { name: "Comprensión", exact: true }).click();
  const comprehension = page.getByRole("region", { name: "Comprensión" });
  await expect(
    comprehension.getByText("Hipótesis de la IA").first(),
  ).toBeVisible({ timeout: 30000 });
  await comprehension.getByRole("tab", { name: "Columnas" }).click();
  await expect(comprehension).toContainText("De razón");
  await comprehension.getByRole("tab", { name: "Relaciones" }).click();
  await expect(
    comprehension.getByRole("img", {
      name: "Mapa de calor de asociaciones entre columnas",
    }),
  ).toBeVisible();
  const relation = comprehension
    .getByRole("listitem", { name: /Relación Units_Sold – Customer_Name/ })
    .first();
  await expect(relation).toContainText("Los datos no la respaldan");
  const reject = relation.getByRole("button", { name: "Rechazar" });
  await reject.click();
  await expect(reject).toHaveAttribute("aria-pressed", "true");
  await expect(relation).toContainText("Rechazada");
  // Fase 20 y 25: la exploración guiada es ahora la pestaña Investigación (reglas + IA falsa,
  // cifras calculadas sobre todas las filas); la propuesta inválida queda descartada en el plan.
  await page.getByRole("tab", { name: "Investigación", exact: true }).click();
  const investigationTab = page.getByRole("region", {
    name: "Investigación",
    exact: true,
  });
  const plan = investigationTab.getByRole("table", {
    name: "Plan de investigación",
  });
  await expect(plan).toBeVisible({ timeout: 60000 });
  await expect(plan).toContainText("Propuesta por la IA");
  await expect(plan).toContainText("no es una dimensión");
  // Fase 21: dashboard diseñado por la IA falsa; «Sí va» fija un hallazgo arriba. Desde la
  // Fase 26 vive en su propia pestaña.
  await page.getByRole("tab", { name: "Dashboard", exact: true }).click();
  const adapted = page.getByRole("region", { name: "Dashboard", exact: true });
  await expect(adapted.getByText("Diseñado por la IA")).toBeVisible();
  await expect(
    adapted.getByRole("group", { name: "Lo esencial", exact: true }),
  ).toBeVisible();
  await adapted
    .getByRole("group", { name: "Detalle", exact: true })
    .getByRole("button", { name: "Sí va" })
    .first()
    .click();
  const pinned = adapted.getByRole("group", {
    name: "Fijados por ti",
    exact: true,
  });
  await expect(pinned.getByRole("button", { name: "Sí va" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await adapted.getByText(/Elecciones de diseño rechazadas/).click();
  await expect(adapted).toContainText("No es un elemento publicado.");
  // El informe en PDF se descarga en su pestaña; el progreso termina sin etapas pendientes.
  await openTab(page, "Informe");
  const report = page.getByRole("link", { name: "Descargar PDF" });
  await expect(report).toBeVisible({ timeout: 60_000 });
  await expect(stages).not.toContainText("Pendiente");
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    report.click(),
  ]);
  expect(download.suggestedFilename()).toBe("informe-ventas_mensuales-v1.pdf");
  const pdf = await readFile((await download.path())!);
  expect(pdf.subarray(0, 4).toString()).toBe("%PDF");
});
