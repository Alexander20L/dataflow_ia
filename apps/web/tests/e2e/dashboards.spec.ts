import { expect, test, type Page } from "@playwright/test";
import {
  confirmSemantics,
  csv,
  saveMetric,
  typedVersion,
} from "./analytics-support";

async function addToDashboard(
  page: Page,
  dashboard: { name: string; isNew: boolean },
  card: { title: string; view: string; size?: string },
) {
  const stage = page.getByRole("region", { name: "Análisis de negocio" });
  await stage.getByRole("button", { name: "Añadir a un dashboard" }).click();
  const dialog = page.getByRole("dialog", { name: "Añadir a un dashboard" });
  if (dashboard.isNew) {
    await expect(dialog.getByLabel("Dashboard de destino")).toHaveValue("new");
    await dialog.getByLabel("Nombre del dashboard nuevo").fill(dashboard.name);
  } else {
    await dialog
      .getByLabel("Dashboard de destino")
      .selectOption({ label: dashboard.name });
  }
  await dialog.getByLabel("Título de la tarjeta").fill(card.title);
  await dialog
    .getByLabel("Forma de la tarjeta")
    .selectOption({ label: card.view });
  if (card.size)
    await dialog
      .getByLabel("Tamaño de la tarjeta")
      .selectOption({ label: card.size });
  await dialog.getByRole("button", { name: "Añadir tarjeta" }).click();
  await expect(dialog).toBeHidden();
  await expect(stage.getByText(`Añadida a «${dashboard.name}»`)).toBeVisible();
}

async function calculate(page: Page) {
  const stage = page.getByRole("region", { name: "Análisis de negocio" });
  await stage.getByRole("button", { name: "Calcular" }).click();
  await expect(
    stage.getByRole("table", { name: "Resultado del análisis" }),
  ).toBeVisible({ timeout: 30000 });
}

/** Lo que debe verse igual antes y después de cerrar sesión. */
async function expectSavedDashboard(page: Page) {
  const board = page.getByRole("region", { name: "Dashboards" });
  await expect(board.getByTestId("dashboard-title")).toHaveText("Ventas 2026");
  await expect(board.getByText("Revisión 4 de 4")).toBeVisible();
  const cards = board.locator("article.dashboard-card");
  await expect(cards).toHaveCount(2);
  // Orden y tamaños guardados: el KPI se movió antes y es pequeño.
  await expect(cards.nth(0)).toHaveAttribute(
    "aria-label",
    "Tarjeta Ingresos totales",
  );
  await expect(cards.nth(0)).toHaveClass(/size-small/);
  await expect(cards.nth(1)).toHaveClass(/size-medium/);
  await expect(
    board.getByRole("button", { name: "De dónde sale Ingresos totales" }),
  ).toHaveText("401.25 EUR", { timeout: 30000 });
  await expect(cards.nth(0).getByTestId("card-meta")).toContainText("v2");
  await expect(cards.nth(0).getByTestId("filter-not-applicable")).toContainText(
    "Filtro no aplicable: region",
  );
  await expect(
    board.getByRole("img", { name: "Ingresos por región: Ingresos" }),
  ).toBeVisible();
  // El filtro global sólo deja la región Norte en la tarjeta que agrupa por región.
  await expect(board.getByText("region = Norte")).toBeVisible();
  await cards.nth(1).getByText("Ver cifras y su procedencia").click();
  const figures = cards.nth(1).locator(".chart-figures li");
  await expect(figures).toHaveCount(1);
  await expect(figures.first()).toHaveText("Norte: 201.00 EUR");
}

test("crear un dashboard con un CSV propio, cerrar sesión, volver y encontrarlo igual", async ({
  page,
}) => {
  // Preparación de v2, semántica y métricas por la API, más dos análisis y el dashboard.
  test.setTimeout(180_000);
  const email = `dashboards-${crypto.randomUUID()}@example.com`;
  const password = "Prueba-segura-12345";
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: { name: "Dashboards", email, password },
  });
  expect(registered.status()).toBe(201);
  await page.goto("/new");
  await page.getByLabel("Nombre del proyecto").fill("Dashboards de ventas");
  await page.locator('input[type="file"]').setInputFiles({
    name: "ventas_calidad.csv",
    mimeType: "text/csv",
    buffer: csv,
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await expect(
    page.getByRole("heading", { name: "Vista previa del CSV", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  const projectPath = new URL(page.url()).pathname;
  await typedVersion(page);
  await confirmSemantics(page.request);
  await saveMetric(page.request, "Ingresos", "sum", "importe");
  await page.reload();
  await expect(
    page.getByRole("status", { name: "Versión que estás viendo" }),
  ).toContainText("Estás viendo v2", { timeout: 20000 });
  const stages = page.getByRole("navigation", { name: "Etapas del CSV real" });

  // 1. Dos análisis añadidos a un dashboard nuevo: barras por región y KPI total.
  await stages.getByRole("button", { name: "Análisis", exact: false }).click();
  const stage = page.getByRole("region", { name: "Análisis de negocio" });
  await stage.getByLabel("Usar Ingresos").check();
  await stage.getByLabel("Agrupar por region", { exact: true }).check();
  await calculate(page);
  await addToDashboard(
    page,
    { name: "Ventas 2026", isNew: true },
    { title: "Ingresos por región", view: "Barras" },
  );
  await stage.getByLabel("Agrupar por region", { exact: true }).uncheck();
  await calculate(page);
  await addToDashboard(
    page,
    { name: "Ventas 2026", isNew: false },
    { title: "Ingresos totales", view: "KPI", size: "Pequeña" },
  );

  // 2. Visualización: mover la tarjeta KPI antes y filtrar por región.
  await stages.getByRole("button", { name: "Visualización" }).click();
  const board = page.getByRole("region", { name: "Dashboards" });
  await expect(board.getByText("Revisión 2 de 2")).toBeVisible();
  await board
    .getByRole("button", { name: "Mover Ingresos totales antes" })
    .click();
  await expect(board.getByText("Revisión 3 de 3")).toBeVisible();
  await board
    .getByLabel("Dimensión del filtro")
    .selectOption({ label: "region" });
  await board.getByLabel("Valores del filtro").fill("Norte");
  await board.getByRole("button", { name: "Aplicar filtro" }).click();
  await expectSavedDashboard(page);

  // 3. «De dónde sale este número» desde la tarjeta.
  await board
    .getByRole("button", { name: "De dónde sale Ingresos totales" })
    .click();
  const provenance = page.getByRole("dialog", {
    name: "De dónde sale este número",
  });
  await expect(provenance.getByTestId("evidence-value")).toHaveText(
    "401.25 EUR",
  );
  await provenance
    .getByRole("button", { name: /cerrar/i })
    .first()
    .click();

  // 4. Cerrar sesión, volver a entrar y encontrarlo igual.
  await page.goto("/settings");
  await page
    .getByRole("button", { name: "Cerrar sesión", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Bienvenido de nuevo" }),
  ).toBeVisible();
  await page.getByLabel("Correo electrónico").fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Iniciar sesión", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Cerrar sesión", exact: true }),
  ).toBeVisible();
  await page.goto(projectPath);
  await expect(
    page.getByRole("status", { name: "Versión que estás viendo" }),
  ).toContainText("Estás viendo v2", { timeout: 20000 });
  await stages.getByRole("button", { name: "Visualización" }).click();
  await expectSavedDashboard(page);

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false);
});
