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
});
