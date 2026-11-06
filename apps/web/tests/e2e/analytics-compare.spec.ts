import { expect, test } from "@playwright/test";
import {
  confirmSemantics,
  csv,
  saveMetric,
  typedVersion,
} from "./analytics-support";

test("top N con empate declarado, % del total y comparación con el periodo anterior, con procedencia", async ({
  page,
}) => {
  // Incluye la preparación de v2, la semántica y las métricas por la API.
  test.setTimeout(120_000);
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Comparaciones",
      email: `compare-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-12345",
    },
  });
  expect(registered.status()).toBe(201);
  await page.goto("/new");
  await page.getByLabel("Nombre del proyecto").fill("Ranking de ventas");
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
  await confirmSemantics(page.request);
  await saveMetric(page.request, "Ingresos", "sum", "importe");
  await saveMetric(page.request, "Operaciones", "count", "id");
  await page.reload();
  await expect(
    page.getByRole("status", { name: "Versión que estás viendo" }),
  ).toContainText("Estás viendo v2", { timeout: 20000 });
  const stages = page.getByRole("navigation", { name: "Etapas del CSV real" });
  await stages.getByRole("button", { name: "Análisis", exact: false }).click();
  const stage = page.getByRole("region", { name: "Análisis de negocio" });
  await expect(stage.getByText("Revisión semántica 1")).toBeVisible();

  // 1. Top 3 regiones por operaciones y % del total de ingresos.
  await stage.getByLabel("Usar Ingresos").check();
  await stage.getByLabel("Usar Operaciones").check();
  await stage.getByLabel("Agrupar por region", { exact: true }).check();
  await stage.getByLabel("Ordenar por").selectOption({ label: "Operaciones" });
  await stage.getByLabel("Top N", { exact: true }).fill("3");
  await stage.getByLabel("% del total de Ingresos").check();
  await stage.getByRole("button", { name: "Calcular" }).click();
  const results = stage.getByRole("table", { name: "Resultado del análisis" });
  await expect(results.locator("thead")).toContainText("Posición", {
    timeout: 30000,
  });
  await expect(results.locator("thead")).toContainText("% del total");
  const rows = results.locator("tbody tr");
  await expect(rows).toHaveCount(3);
  // Norte 3 operaciones; Este y Oeste 1: Oeste va detrás por la región y se marca «=».
  await expect(rows.nth(0)).toContainText("Norte");
  await expect(rows.nth(0)).toContainText("50.09 %");
  await expect(rows.nth(1)).toContainText("Este");
  await expect(rows.nth(1)).toContainText("29.97 %");
  await expect(rows.nth(2)).toContainText("Oeste");
  await expect(
    rows.nth(2).getByRole("button", { name: "Posición de Oeste" }),
  ).toHaveText("3 =");
  await expect(stage.getByTestId("ranking-note")).toContainText(
    "1 grupo(s) oculto(s)",
  );
  await expect(stage.getByTestId("share-note")).toContainText(
    "incluidos los que no se muestran",
  );

  const provenance = page.getByRole("dialog", {
    name: "De dónde sale este número",
  });
  await rows.nth(2).getByRole("button", { name: "Posición de Oeste" }).click();
  await expect(provenance.getByTestId("evidence-value")).toHaveText("3");
  await expect(provenance.getByTestId("evidence-rank")).toContainText(
    "Mismo valor que la posición anterior",
  );
  await provenance
    .getByRole("button", { name: /cerrar/i })
    .first()
    .click();
  await rows
    .nth(0)
    .getByRole("button", { name: "% del total de Ingresos Norte" })
    .click();
  await expect(provenance.getByTestId("evidence-value")).toHaveText("50.09 %");
  await expect(provenance.getByTestId("evidence-share-total")).toContainText(
    "401.25 EUR en 3 grupo(s)",
  );
  await provenance
    .getByRole("button", { name: /cerrar/i })
    .first()
    .click();

  // 2. Con comparaciones, un periodo que no empieza en un límite completo no se calcula.
  await stage.getByLabel("Usar Ingresos").uncheck();
  await stage.getByLabel("Agrupar por region", { exact: true }).uncheck();
  await stage.getByLabel("Agrupar por tiempo").selectOption("month");
  await stage.getByLabel("Desde").fill("2026-01-03");
  await stage.getByLabel("Comparar con periodo anterior").check();
  await stage.getByRole("button", { name: "Calcular" }).click();
  await expect(
    stage.getByRole("alert", { name: "Requisitos pendientes" }),
  ).toContainText("primer día de un mes");

  // 3. Por día, del 3 al 5 de enero: el 3 se compara con el 2, fuera del periodo consultado.
  await stage.getByLabel("Agrupar por tiempo").selectOption("day");
  await stage.getByLabel("Hasta").fill("2026-01-05");
  await stage.getByRole("button", { name: "Calcular" }).click();
  await expect(results.locator("thead")).toContainText("Periodo anterior", {
    timeout: 30000,
  });
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0)).toContainText("2026-01-03");
  await expect(rows.nth(0)).toContainText("0.00 %");
  await rows
    .nth(0)
    .getByRole("button", {
      name: "Operaciones periodo anterior 2026-01-03",
    })
    .click();
  await expect(provenance.getByTestId("evidence-cell")).toContainText(
    "Periodo anterior",
  );
  await expect(provenance.getByTestId("evidence-base")).toContainText(
    "2026-01-02 · base 1",
  );
  await expect(provenance.getByTestId("evidence-base-counts")).toHaveText(
    "6 de entrada · 0 excluidas por filtros · 3 fuera de los periodos base · 0 excluidas por nulos · 3 incluidas",
  );
  await expect(provenance.getByTestId("evidence-counts")).toHaveText(
    "6 de entrada · 3 excluidas por filtros · 0 excluidas por nulos · 3 incluidas",
  );
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
