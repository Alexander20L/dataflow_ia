import { readFile } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";

// Fase 25: pestaña Investigación. El plan (pregunta, motivo, columnas, método, prioridad y
// dependencias), el árbol de investigaciones secundarias, la evidencia de cada resultado con su
// clase y el historial; «Volver a investigar» conserva la investigación anterior.
test("Investigación: plan, árbol, evidencias e historial", async ({ page }) => {
  test.setTimeout(150_000);
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista Investigación",
      email: `investigacion-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-Investigacion-123",
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
  await page
    .getByRole("tab", { name: "Investigación", exact: true })
    .click({ timeout: 30000 });
  const tab = page.getByRole("region", { name: "Investigación", exact: true });

  // Plan: la evolución mensual va primero y la comparación de periodos depende de ella.
  const plan = tab.getByRole("table", { name: "Plan de investigación" });
  await expect(plan).toBeVisible({ timeout: 60000 });
  const first = plan.getByRole("row", { name: "Investigación 1", exact: true });
  await expect(first).toContainText("¿Cómo evoluciona Revenue mes a mes?");
  await expect(first).toContainText("Serie temporal mensual");
  await expect(first).toContainText("Alta");
  await expect(
    plan.getByRole("row", { name: "Investigación 2", exact: true }),
  ).toContainText("Comparación de periodos");

  // Árbol: hay investigaciones secundarias (ids con punto).
  await tab.getByRole("tab", { name: "Árbol" }).click();
  await expect(
    tab.getByRole("listitem", { name: /^Investigación \d+\.\d+$/ }).first(),
  ).toBeVisible();

  // Evidencias: cada resultado dice sus registros, su operación y su evaluación.
  await tab.getByRole("tab", { name: /^Evidencias/ }).click();
  const evidence = tab.getByRole("article", {
    name: "Evidencia 1",
    exact: true,
  });
  await expect(evidence).toContainText("Registros considerados");
  await expect(evidence).toContainText("Magnitud del efecto");
  await expect(
    evidence.getByRole("img", { name: /Evolución mensual/ }),
  ).toBeVisible();

  // Volver a investigar: la anterior queda en el historial y se puede consultar.
  await tab.getByRole("button", { name: "Volver a investigar" }).click();
  await expect(
    tab.getByRole("button", { name: "Volver a investigar" }),
  ).toBeVisible({ timeout: 60000 });
  await tab.getByRole("tab", { name: "Historial" }).click();
  const history = tab.getByRole("table", {
    name: "Investigaciones anteriores",
  });
  await expect(history.getByRole("row")).toHaveCount(3);
  await expect(history).toContainText("Volver a investigar");
  await expect(history).toContainText("Al cargar el archivo");
  await history.getByRole("button", { name: "Ver" }).click();
  await expect(tab).toContainText("Estás viendo una investigación anterior.");
  await tab.getByRole("button", { name: "Volver a la actual" }).click();
  await expect(tab).not.toContainText(
    "Estás viendo una investigación anterior.",
  );
});
