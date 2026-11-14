import { expect, test } from "@playwright/test";
import { openAnalysis } from "./helpers";

test("subir CSV muestra el dashboard guardado sin ningún paso manual", async ({
  page,
}) => {
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista automático",
      email: `automatic-${crypto.randomUUID()}@example.com`,
      password: "Prueba-automatica-segura-123",
    },
  });
  expect(registration.status()).toBe(201);
  const failedRequests: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/v1/") && response.status() >= 400)
      failedRequests.push(`${response.status()} ${response.url()}`);
  });
  await page.goto("/new");
  await page.locator('input[type="file"]').setInputFiles({
    name: "datos.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "id,fecha,region,importe\n001,2026-01-01,Norte,10\n002,2026-01-02,Sur,20\n003,2026-02-01,Norte,30\n004,2026-02-02,Sur,\n",
    ),
  });
  await expect(page.getByLabel("Nombre del proyecto")).toHaveValue("datos");
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await openAnalysis(page);
  const dashboard = page.getByRole("region", {
    name: "Dashboard automático",
    exact: true,
  });
  await expect(
    dashboard.getByRole("heading", { name: "Tu análisis automático" }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    dashboard.getByRole("heading", { name: "Total de importe" }),
  ).toBeVisible();
  const interpretation = dashboard.getByRole("region", {
    name: "Lectura automática de los datos",
  });
  await expect(
    interpretation.getByRole("heading", {
      name: "Posible contexto comercial (ventas)",
    }),
  ).toBeVisible();
  await expect(
    interpretation.getByRole("button", {
      name: /confirmar|guardar|aplicar|elegir/i,
    }),
  ).toHaveCount(0);
  await expect(
    dashboard.getByRole("img", { name: "importe por mes" }),
  ).toBeVisible();
  await expect(
    dashboard.getByRole("img", { name: "importe por region" }),
  ).toBeVisible();
  await expect(
    dashboard.getByText("3 valores utilizados · 1 vacíos excluidos").first(),
  ).toBeVisible();
  // Fase 13: no quedan herramientas manuales ni etapas que abrir.
  await expect(
    page.getByRole("button", { name: /Herramientas avanzadas/ }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("navigation", { name: "Etapas del CSV real" }),
  ).toHaveCount(0);
  // Fase 27: la explicación de la IA (resumen, conclusiones y recomendaciones con cifras
  // verificadas) está en el informe.
  await page.getByRole("tab", { name: "Informe", exact: true }).click();
  const report = page.getByRole("region", { name: "Informe", exact: true });
  const conclusions = report.getByRole("region", {
    name: "Conclusiones y recomendaciones",
  });
  await expect(conclusions).toContainText("Recomendaciones", {
    timeout: 60000,
  });
  const savedConclusions = await conclusions.innerText();
  await page.getByRole("tab", { name: "Análisis", exact: true }).click();
  await dashboard.getByText("Detalle de los datos", { exact: true }).click();
  await expect(
    dashboard.getByRole("cell", { name: "001", exact: true }),
  ).toBeVisible();
  const projectId = page.url().split("/workspace/")[1]?.split("/")[0];
  expect(projectId).toBeTruthy();
  // Las rutas del recorrido manual y del pipeline por política ya no existen.
  for (const retired of [
    `/api/v1/projects/${projectId}/automation-policy`,
    `/api/v1/projects/${projectId}/plans`,
    `/api/v1/projects/${projectId}/dashboards`,
  ])
    expect((await page.request.get(retired)).status()).toBe(404);
  await page.reload();
  // El informe guardado no cambia al volver.
  await page.getByRole("tab", { name: "Informe", exact: true }).click();
  await expect(conclusions).toHaveText(savedConclusions.replace(/\s+/g, " "), {
    useInnerText: true,
  });
  await openAnalysis(page);
  await expect(
    dashboard.getByRole("heading", { name: "Tu análisis automático" }),
  ).toBeVisible();
  await expect(
    interpretation.getByRole("heading", {
      name: "Posible contexto comercial (ventas)",
    }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await dashboard.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
  ).toBeTruthy();
  expect(failedRequests).toEqual([]);
});
