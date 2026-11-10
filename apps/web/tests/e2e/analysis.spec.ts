import { readFile } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";

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
  const dashboard = page.getByRole("region", {
    name: "Dashboard automático",
    exact: true,
  });
  await expect(
    dashboard.getByRole("heading", { name: "Tu análisis automático" }),
  ).toBeVisible({ timeout: 30000 });
  // Fase 15: los hallazgos aparecen antes del dashboard descriptivo, sin ninguna acción.
  const findings = page.getByRole("region", {
    name: "Hallazgos del análisis automático",
  });
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
  // Fase 16: la investigación sigue los hallazgos (reglas + IA validada) sin ninguna acción.
  const investigation = page.getByRole("region", {
    name: "Investigación automática",
  });
  await expect(
    investigation.getByRole("article", {
      name: "Variación 2024 frente a 2023 por Region",
    }),
  ).toContainText("el mayor aporte por Region es de Norte", { timeout: 30000 });
  await expect(
    investigation.getByRole("article", {
      name: "2024-10: Revenue por Product frente a su nivel habitual",
    }),
  ).toContainText("es Monitor");
  await expect(
    investigation.getByText("Propuesto por la IA").first(),
  ).toBeVisible();
  await expect(
    investigation
      .getByRole("region", { name: "Explicación automática IA" })
      .getByRole("link", { name: /De dónde sale/ }),
  ).toHaveCount(1);
  await investigation.getByText(/Propuestas rechazadas/).click();
  await expect(investigation).toContainText("Ya se investigó");
  await expect(investigation.getByRole("button")).toHaveCount(0);
  // Fase 17: resumen arriba con progreso por etapas e informe PDF descargable.
  const summary = page.getByRole("region", { name: "Resumen" });
  const report = summary.getByRole("link", {
    name: "Descargar informe (PDF)",
  });
  await expect(report).toBeVisible({ timeout: 30_000 });
  await expect(
    summary
      .getByRole("list", { name: "Progreso de la carga" })
      .getByRole("listitem"),
  ).toHaveCount(6);
  await expect(summary).not.toContainText("Pendiente");
  await expect(summary.getByText("Hallazgos principales")).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    report.click(),
  ]);
  expect(download.suggestedFilename()).toBe("informe-ventas_mensuales-v1.pdf");
  const pdf = await readFile((await download.path())!);
  expect(pdf.subarray(0, 4).toString()).toBe("%PDF");
  const reading = dashboard.getByRole("region", {
    name: "Lectura automática de los datos",
  });
  await expect(
    reading.getByRole("heading", {
      name: "Posible contexto comercial (ventas)",
    }),
  ).toBeVisible();
  await expect(reading).toContainText(
    "Periodo mensual (Year + Month): 2023-01 a 2024-12",
  );
  await expect(reading).toContainText("faltan 1: 2024-07");
  await expect(
    reading.getByRole("note", { name: "Análisis limitados" }),
  ).toContainText("Análisis por Customer o Customer_Name");
  // El año no se promedia y el importe se suma sin inventar moneda.
  await expect(dashboard.getByRole("heading", { name: /Year/ })).toHaveCount(0);
  await expect(
    dashboard.getByRole("heading", { name: "Total de Revenue" }),
  ).toBeVisible();
  await expect(
    dashboard.getByRole("img", { name: "Revenue por mes" }),
  ).toBeVisible();
  await expect(
    dashboard.getByRole("img", { name: "Revenue por Product" }),
  ).toBeVisible();
  await expect(
    dashboard.getByRole("img", { name: /Customer_Name/ }),
  ).toHaveCount(0);
  const quality = dashboard.getByRole("region", {
    name: "Calidad de los datos",
  });
  await expect(quality).toContainText("Customer con varios Customer_Name");
  await expect(quality).toContainText("Meses sin registros");
  await expect(quality).toContainText("Valores atípicos en Units_Sold");
  await expect(quality.getByRole("button")).toHaveCount(0);
  // Fase 19: entendimiento del negocio (IA falsa) y valoración opcional de una relación.
  const comprehension = page.getByRole("region", {
    name: "Entendimiento del negocio",
  });
  await expect(
    comprehension.getByText("Hipótesis de la IA").first(),
  ).toBeVisible();
  await expect(comprehension).toContainText("De razón");
  await expect(
    comprehension.getByRole("img", {
      name: "Mapa de calor de asociaciones entre columnas",
    }),
  ).toBeVisible();
  const relation = comprehension
    .getByRole("listitem", { name: /Relación Units_Sold – Customer_Name/ })
    .first();
  await expect(relation).toContainText("Los datos no la respaldan");
  const notRelevant = relation.getByRole("button", { name: "No relevante" });
  await notRelevant.click();
  await expect(notRelevant).toHaveAttribute("aria-pressed", "true");
  // Fase 20: exploración guiada (reglas + IA falsa) con cifras calculadas sobre todas las filas.
  const exploration = page.getByRole("region", { name: "Exploración guiada" });
  await expect(
    exploration.getByText("Juzgada por la IA").first(),
  ).toBeVisible();
  await exploration
    .getByText(/Propuestas rechazadas por la validación/)
    .click();
  await expect(exploration).toContainText("no es una dimensión");
  await expect(exploration.getByRole("button")).toHaveCount(0);
  // Fase 21: dashboard diseñado por la IA falsa; «Sí va» fija un hallazgo arriba.
  const adapted = page.getByRole("region", { name: "Dashboard adaptado" });
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
  // El informe anterior sigue descargable mientras se genera el nuevo con esa marca.
  await expect(
    summary.getByRole("link", { name: /Descargar informe/ }),
  ).toBeVisible();
});
