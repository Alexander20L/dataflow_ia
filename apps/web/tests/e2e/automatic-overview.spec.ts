import { expect, test } from "@playwright/test";
import { openTab } from "./helpers";

test("subir CSV muestra los resultados guardados sin ningún paso manual", async ({
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
  // Fase 28: los resultados viven en las cinco pestañas; no queda «Análisis».
  await openTab(page, "Dataset");
  await page.getByRole("tab", { name: "Registros" }).click({ timeout: 30000 });
  await expect(
    page.getByRole("cell", { name: "001", exact: true }).first(),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    page.getByRole("tab", { name: "Análisis", exact: true }),
  ).toHaveCount(0);
  // Fase 13: no quedan herramientas manuales ni etapas que abrir.
  await expect(
    page.getByRole("button", { name: /Herramientas avanzadas/ }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("navigation", { name: "Etapas del CSV real" }),
  ).toHaveCount(0);
  await openTab(page, "Dashboard");
  const board = page.getByRole("region", { name: "Dashboard", exact: true });
  await expect(board.getByText(/Dataset completo: /)).toBeVisible({
    timeout: 60000,
  });
  // Fase 27: la explicación de la IA (resumen, conclusiones y recomendaciones con cifras
  // verificadas) está en el informe.
  await openTab(page, "Informe");
  const report = page.getByRole("region", { name: "Informe", exact: true });
  const conclusions = report.getByRole("region", {
    name: "Conclusiones y recomendaciones",
  });
  await expect(conclusions).toContainText("Recomendaciones", {
    timeout: 60000,
  });
  const savedConclusions = await conclusions.innerText();
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
  await openTab(page, "Informe");
  await expect(conclusions).toHaveText(savedConclusions.replace(/\s+/g, " "), {
    useInnerText: true,
  });
  await openTab(page, "Dashboard");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(board.getByText(/Dataset completo: /)).toBeVisible();
  expect(
    await board.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
  ).toBeTruthy();
  expect(failedRequests).toEqual([]);
});
