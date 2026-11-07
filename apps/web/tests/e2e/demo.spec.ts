import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  const response = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Alex",
      email: `demo-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-12345",
    },
  });
  expect(response.status()).toBe(201);
});

test("la limpieza exige aprobación, conserva v1 y persiste al recargar", async ({
  page,
}) => {
  await page.goto("/workspace/ventas-2026");
  await page.getByRole("button", { name: "Calidad", exact: false }).click();
  await expect(
    page.getByText("8 registros · columna importe", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Revisar propuesta de limpieza" })
    .click();
  await expect(
    page.getByRole("button", { name: "Ejecutar limpieza aprobada" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Aprobar", exact: true }).click();
  await page
    .getByRole("button", { name: "Ejecutar limpieza aprobada" })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Confirmar y crear v2" }).click();
  await expect(
    page.getByText("Limpieza demostrativa completada · v1 → v2"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Ingesta", exact: false }).click();
  await expect(
    page.getByText("232 registros", { exact: false }).first(),
  ).toBeVisible();
  await page.getByLabel("Versión del dataset").selectOption("v1");
  await expect(
    page.getByText("240 registros", { exact: false }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "nulo", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("232 registros", { exact: false }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Calidad", exact: false }).click();
  await expect(
    page.getByText("No hay importes faltantes en esta versión."),
  ).toBeVisible();
});

test("un archivo de usuario no recibe resultados del fixture", async ({
  page,
}) => {
  await page.goto("/new");
  await page.getByLabel("Nombre del proyecto").fill("Mis ventas privadas");
  await page.locator('input[type="file"]').setInputFiles({
    name: "datos.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("id,importe\n1,90\n"),
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await expect(
    page.getByRole("heading", { name: "Mis ventas privadas" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Tu análisis automático", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  await page
    .getByRole("region", { name: "Dashboard automático", exact: true })
    .getByText("Detalle de los datos", { exact: true })
    .click();
  await expect(
    page.getByRole("cell", { name: "90", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Dataset sintético", { exact: true }),
  ).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Mis ventas privadas" }),
  ).toBeVisible();
  await page.goto("/projects");
  await page.getByLabel("Buscar en proyectos").fill("privadas");
  await expect(
    page.getByRole("link", { name: "Abrir Mis ventas privadas", exact: true }),
  ).toBeVisible();
});

test("filtrar métricas cambia resultados y exporta sólo el fixture seleccionado", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/workspace/ventas-2026");
  await page
    .getByRole("button", { name: "Análisis", exact: false })
    .filter({ has: page.locator(".step-number") })
    .click();
  const before = await page.locator(".mini-metrics strong").first().innerText();
  await page.getByLabel("Filtrar región").selectOption("Norte");
  await expect(page.locator(".mini-metrics strong").first()).not.toHaveText(
    before,
  );
  await page.getByRole("button", { name: "Ver definición del KPI" }).click();
  await expect(page.getByRole("dialog")).toContainText("Norte");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "CSV demo" }).click();
  expect((await download).suggestedFilename()).toBe("ventas-demo-v1.csv");
  expect(errors).toEqual([]);
});

test("navegación móvil, tema persistente y ruta desconocida", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Hola, Alex/ })).toBeVisible();
  await page.getByLabel("Abrir navegación").click();
  await page.getByRole("button", { name: "Modo oscuro" }).click();
  await expect(page.locator("html")).toHaveClass("dark");
  await page
    .getByLabel("Cerrar navegación")
    .click({ position: { x: 350, y: 400 } });
  await page.reload();
  await expect(page.locator("html")).toHaveClass("dark");
  const overflowing = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflowing).toBe(false);
  await page.goto("/ruta-inexistente");
  await expect(
    page.getByRole("heading", { name: "Página no encontrada" }),
  ).toBeVisible();
});
