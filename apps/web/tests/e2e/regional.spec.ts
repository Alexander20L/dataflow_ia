import { readFile } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";

// Fase 18: un CSV guardado por Excel en Windows (ANSI, punto y coma, coma decimal y fechas
// día/mes/año) se lee sin preguntar nada y la lectura se explica.
test("CSV regional: se lee solo y se explica cómo", async ({ page }) => {
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista Fase 18",
      email: `fase18-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-Fase18-123",
    },
  });
  expect(registration.status()).toBe(201);
  const rows = [
    "Región;Fecha;Importe;Unidades",
    "Bogotá;31/01/2024;1.234,50;3",
    "Medellín;29/02/2024;980,25;2",
    "Bogotá;31/03/2024;2.000,00;5",
    "Cali;30/04/2024;1.500,75;4",
  ];
  // Windows-1252 coincide con Latin-1 en estos caracteres.
  const csv = Buffer.from(rows.join("\r\n") + "\r\n", "latin1");
  await page.goto("/new");
  await page.locator('input[type="file"]').setInputFiles({
    name: "ventas_regional.csv",
    mimeType: "text/csv",
    buffer: csv,
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  const reading = page.getByRole("region", { name: "Lectura del archivo" });
  await expect(reading).toContainText("Windows-1252 (ANSI)", {
    timeout: 30000,
  });
  await expect(reading).toContainText("separador punto y coma");
  await expect(reading).toContainText(
    "Importe: Leída como coma decimal y punto de miles",
  );
  await expect(reading).toContainText("Fecha: Leída como día/mes/año");
  await expect(reading.getByRole("button")).toHaveCount(0);
});

// Fase 18B: un PDF con dos tablas da dos versiones; cada una dice de qué tabla sale.
test("PDF con tablas: cada tabla se analiza sola", async ({ page }) => {
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista PDF",
      email: `fase18b-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-Fase18-123",
    },
  });
  expect(registration.status()).toBe(201);
  const pdf = await readFile(
    path.join(__dirname, "fixtures", "ventas_tablas.pdf"),
  );
  await page.goto("/new");
  await page.locator('input[type="file"]').setInputFiles({
    name: "ventas_tablas.pdf",
    mimeType: "application/pdf",
    buffer: pdf,
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  const origin = page.getByRole("note", { name: "Origen de los datos" });
  await expect(origin).toContainText("Tabla 1 de la página 1 del PDF.", {
    timeout: 30000,
  });
  await expect(origin).toContainText("Tabla 2 de la página 1");
  await expect(
    page.getByRole("region", { name: "Lectura del archivo" }),
  ).toContainText("Importe: Leída como coma decimal y punto de miles", {
    timeout: 30000,
  });
});

// Fase 18B: sin servidores permitidos, la conexión a SQL Server explica que está desactivada.
test("SQL Server desactivado: se explica sin guardar nada", async ({
  page,
}) => {
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista SQL",
      email: `fase18c-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-Fase18-123",
    },
  });
  expect(registration.status()).toBe(201);
  await page.goto("/new");
  const panel = page.getByRole("region", { name: "Conectar SQL Server" });
  await panel.getByRole("button", { name: "Conectar" }).click();
  await panel.getByLabel("Servidor").fill("sql.example.com");
  await panel.getByLabel("Base de datos").fill("ventas");
  await panel.getByLabel("Usuario").fill("lector");
  await panel.getByLabel("Contraseña").fill("no-se-guarda");
  await panel.getByRole("button", { name: "Copiar tablas y analizar" }).click();
  await expect(panel.getByRole("alert")).toContainText(
    "no está activada en este entorno",
  );
  await expect(panel.getByLabel("Contraseña")).toHaveValue("");
});
