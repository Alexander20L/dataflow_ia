import { readFile } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";

// Fase 26: pestaña Dashboard. Indicadores con su origen, filtros que recalculan lo que depende
// de ellos y una versión personalizada que no destruye la automática.
test("Dashboard: indicadores con origen, filtros y versión personalizada", async ({
  page,
}) => {
  test.setTimeout(150_000);
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista Dashboard",
      email: `dashboard-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-Dashboard-123",
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
    .getByRole("tab", { name: "Dashboard", exact: true })
    .click({ timeout: 30000 });
  const board = page.getByRole("region", { name: "Dashboard", exact: true });
  await expect(board.getByText("Diseñado por la IA")).toBeVisible({
    timeout: 90000,
  });
  await expect(board.getByText(/Dataset completo: /)).toBeVisible();

  // Cada indicador dice de dónde sale.
  const kpi = board.locator(".dashboard-kpi").first();
  await kpi.getByText("Origen").click();
  await expect(kpi).toContainText("Cálculo del dashboard");
  await expect(kpi).toContainText("Registros utilizados");

  // Filtro por periodo: indicadores y gráficos dicen que muestran un subconjunto.
  const filters = board.getByRole("form", { name: "Filtros del dashboard" });
  const from = filters.getByLabel("Desde");
  const months = await from.locator("option").count();
  await from.selectOption({ index: months - 2 });
  await filters.getByRole("button", { name: "Aplicar filtros" }).click();
  await expect(board.getByText(/Subconjunto filtrado: \d/)).toBeVisible({
    timeout: 30000,
  });
  await expect(
    board.getByText(/^Subconjunto filtrado · Periodo: /).first(),
  ).toBeVisible();
  await filters.getByRole("button", { name: "Quitar filtros" }).click();
  await expect(board.getByText(/Dataset completo: /)).toBeVisible();

  // Personalizar: renombrar la primera sección y ocultar un gráfico.
  await board.getByRole("button", { name: "Personalizar" }).click();
  const editor = board.getByRole("region", {
    name: "Personalizar el dashboard",
  });
  const first = editor.getByLabel("Título de la sección 1");
  const original = await first.inputValue();
  await first.fill("Mi resumen");
  await editor
    .getByRole("button", { name: /^Ocultar / })
    .first()
    .click();
  await editor.getByRole("button", { name: "Guardar mi versión" }).click();
  await expect(
    board.getByRole("tab", { name: "Personalizado (revisión 1)" }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(
    board.getByRole("group", { name: "Mi resumen", exact: true }),
  ).toBeVisible();
  // La versión automática se conserva.
  await board.getByRole("tab", { name: "Automático" }).click();
  await expect(
    board.getByRole("group", { name: original, exact: true }),
  ).toBeVisible();
});
