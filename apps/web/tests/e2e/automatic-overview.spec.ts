import { expect, test } from "@playwright/test";

test("subir CSV muestra dashboard guardado sin políticas ni confirmaciones", async ({
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
  const advancedRequests: string[] = [];
  page.on("request", (request) => {
    if (
      /\/api\/v1\/.*(?:automation-policy|semantic-contracts|\/plans|\/copilot\/|\/understanding)/.test(
        request.url(),
      )
    )
      advancedRequests.push(request.url());
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
  const dashboard = page.getByRole("region", {
    name: "Dashboard automático",
    exact: true,
  });
  await expect(
    dashboard.getByRole("heading", { name: "Tu análisis automático" }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    dashboard.getByRole("heading", { name: "Promedio de importe" }),
  ).toBeVisible();
  const interpretation = dashboard.getByRole("region", {
    name: "Lectura automática de los datos",
  });
  await expect(
    interpretation.getByRole("heading", { name: "Posible contexto de ventas" }),
  ).toBeVisible();
  await expect(
    interpretation.getByRole("button", {
      name: /confirmar|guardar|aplicar|elegir/i,
    }),
  ).toHaveCount(0);
  await expect(
    dashboard.getByRole("img", { name: "Registros por mes de fecha" }),
  ).toBeVisible();
  await expect(
    dashboard.getByRole("img", { name: "Registros por region" }),
  ).toBeVisible();
  await expect(
    dashboard.getByText("3 valores utilizados · 1 vacíos excluidos").first(),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Etapas del CSV real" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "Revisión semántica", exact: true }),
  ).toHaveCount(0);
  expect(advancedRequests).toEqual([]);
  const explanation = page.getByRole("region", {
    name: "Explicación automática IA",
  });
  await expect(
    explanation.getByRole("heading", { name: "Recomendaciones" }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    explanation.getByRole("link", { name: /De dónde sale/ }),
  ).toHaveCount(1);
  await expect(explanation.getByRole("button")).toHaveCount(0);
  const savedExplanation = await explanation.innerText();
  await dashboard.getByText("Detalle de los datos", { exact: true }).click();
  await expect(
    dashboard.getByRole("cell", { name: "001", exact: true }),
  ).toBeVisible();
  const projectId = page.url().split("/workspace/")[1]?.split("/")[0];
  expect(projectId).toBeTruthy();
  const policy = await page.request.get(
    `/api/v1/projects/${projectId}/automation-policy`,
  );
  expect((await policy.json()).revision).toBeNull();
  await page.reload();
  await expect(explanation).toHaveText(savedExplanation.replace(/\s+/g, " "), {
    useInnerText: true,
  });
  await expect(
    dashboard.getByRole("heading", { name: "Tu análisis automático" }),
  ).toBeVisible();
  await expect(
    interpretation.getByRole("heading", { name: "Posible contexto de ventas" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await dashboard.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
  ).toBeTruthy();
  await expect(
    page.getByRole("navigation", { name: "Etapas del CSV real" }),
  ).toHaveCount(0);
  await page
    .getByRole("button", {
      name: "Herramientas avanzadas (opcionales)",
      exact: true,
    })
    .click();
  await page
    .getByRole("navigation", { name: "Etapas del CSV real" })
    .getByRole("button", { name: /Entendimiento/ })
    .click();
  const editor = page.getByRole("region", {
    name: "Revisión semántica",
    exact: true,
  });
  await editor
    .getByLabel("Descripción del dataset")
    .fill("Borrador avanzado opcional");
  await page
    .getByRole("button", { name: "Ocultar herramientas avanzadas" })
    .click();
  const warning = page.getByRole("dialog", {
    name: "Hay cambios semánticos sin guardar",
  });
  await expect(warning).toBeVisible();
  await warning.getByRole("button", { name: "Seguir editando" }).click();
  await expect(editor.getByLabel("Descripción del dataset")).toHaveValue(
    "Borrador avanzado opcional",
  );
  await page
    .getByRole("button", { name: "Ocultar herramientas avanzadas" })
    .click();
  await warning.getByRole("button", { name: "Descartar y continuar" }).click();
  await expect(editor).toHaveCount(0);
  await expect(
    dashboard.getByRole("heading", { name: "Tu análisis automático" }),
  ).toBeVisible();
});
