import { readFile } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { openRecords, openTab } from "./helpers";

// Fase 13B: un libro con portada y título se importa sin elegir hoja ni cabecera.
test("Excel desde el asistente: el sistema elige la hoja y lo explica", async ({
  page,
}) => {
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista Excel",
      email: `xlsx-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-Excel-123",
    },
  });
  expect(registration.status()).toBe(201);
  const book = await readFile(
    path.join(__dirname, "fixtures", "libro_ventas.xlsx"),
  );
  await page.goto("/new");
  await page.locator('input[type="file"]').setInputFiles({
    name: "libro_ventas.xlsx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: book,
  });
  await expect(page.getByLabel("Nombre del proyecto")).toHaveValue(
    "libro_ventas",
  );
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await openTab(page, "Dataset");
  const note = page.getByRole("note", { name: "Hoja importada" });
  await expect(note).toContainText("Se importó la hoja «Ventas»");
  await expect(note).toContainText("cabecera en la fila 3");
  await expect(note).toContainText("No se importaron: la hoja «Notas»");
  await expect(page.getByLabel("Hoja o tabla")).toHaveCount(0);
  await openRecords(page);
  await expect(
    page.getByRole("cell", { name: "2026-01-02", exact: true }).first(),
  ).toBeVisible({ timeout: 30000 });
});
