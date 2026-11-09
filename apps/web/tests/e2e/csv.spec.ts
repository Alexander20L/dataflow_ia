import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

const csv = Buffer.from(
  "﻿id,importe,region,unidades\r\n001,10.50,Norte,1\r\n002,,Sur,2\r\n001,10.50,Norte,1\r\n003, ,Sur,4\r\n",
);
test.beforeEach(async ({ page }) => {
  const result = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista CSV",
      email: `csv-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-CSV-123",
    },
  });
  expect(result.status()).toBe(201);
});

test("CSV real: dashboard automático, descarga íntegra y versiones independientes", async ({
  page,
}) => {
  await page.goto("/new");
  await page
    .getByLabel("Nombre del proyecto")
    .fill("Calidad de mis ventas CSV");
  await page.locator('input[type="file"]').setInputFiles({
    name: "ventas_privadas.csv",
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
  ).toBeVisible({ timeout: 20000 });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Descargar original" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("ventas_privadas.csv");
  expect(await readFile((await download.path())!)).toEqual(csv);

  await page
    .getByRole("button", { name: "Subir nueva versión", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Archivo CSV o Excel")
    .setInputFiles({
      name: "ventas_v2.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("id,importe\n009,25\n"),
    });
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Subir y analizar", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("option", { name: /v2 · ventas_v2.csv/ }),
  ).toHaveCount(1);
  await expect(
    dashboard.getByRole("heading", { name: "Tu análisis automático" }),
  ).toBeVisible({ timeout: 20000 });
  await dashboard
    .locator("summary", { hasText: "Detalle de los datos" })
    .click();
  await expect(
    dashboard.getByRole("cell", { name: "009", exact: true }),
  ).toBeVisible();

  const v1 = await page
    .getByRole("option", { name: /v1 · ventas_privadas.csv/ })
    .getAttribute("value");
  await page.getByLabel("Versión", { exact: true }).selectOption(v1!);
  await dashboard
    .locator("summary", { hasText: "Detalle de los datos" })
    .click();
  await expect(
    dashboard.getByRole("cell", { name: "002", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Calidad de mis ventas CSV" }),
  ).toBeVisible();
  await expect(
    page.getByRole("option", { name: /v1 · ventas_privadas.csv/ }),
  ).toHaveCount(1);
});

test("un CSV inválido muestra un error real y conserva su original", async ({
  page,
}) => {
  await page.goto("/new");
  await page
    .getByLabel("Nombre del proyecto")
    .fill("CSV con estructura incorrecta");
  await page.locator('input[type="file"]').setInputFiles({
    name: "incorrecto.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("id,importe\n1\n"),
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await expect(
    page.getByRole("heading", { name: "No se pudo procesar este archivo" }),
  ).toBeVisible({ timeout: 20000 });
  await expect(page.getByText("CSV_SHAPE", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Descargar original" }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Dashboard automático", exact: true }),
  ).toHaveCount(0);
});
