import { expect, test } from "@playwright/test";

// Fase 22: la pestaña Dataset se abre primero y todo viene del servidor: indicadores sobre el
// archivo completo, registros paginados, perfil por columna, diccionario editable, calidad y
// lectura del archivo. 6 registros × 5 columnas con un nulo → completitud 29/30 = 96,67 %.
test("Dataset: inspección completa y corrección manual persistente", async ({
  page,
}) => {
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista Dataset",
      email: `dataset-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-Dataset-123",
    },
  });
  expect(registration.status()).toBe(201);
  await page.goto("/new");
  await page.locator('input[type="file"]').setInputFiles({
    name: "conocido.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "codigo,region,unidades,precio,estado\n" +
        "00125,Norte,3,10.5,activo\n" +
        "00126,Sur,1,20,N/A\n" +
        "00127,Norte,2,,activo\n" +
        "00128,Este,5,7.25,-\n" +
        "00129,Sur,4,12,activo\n" +
        "00125,Norte,3,10.5,activo\n",
    ),
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  const tab = page.getByRole("tab", { name: "Dataset", exact: true });
  await expect(tab).toHaveAttribute("aria-selected", "true", {
    timeout: 30000,
  });
  const metrics = page.getByRole("region", { name: "Dataset" });
  const indicators = metrics.getByLabel("Indicadores del dataset");
  await expect(indicators).toContainText("Celdas30", { timeout: 30000 });
  await expect(indicators).toContainText("Completitud96,67 %");
  await expect(indicators).toContainText("Filas duplicadas1");
  await expect(indicators).toContainText("Valores faltantes1");

  // Registros: paginados en el servidor, con nulos visibles y búsqueda.
  await page.getByRole("tab", { name: "Registros" }).click();
  const table = page.getByRole("table");
  await expect(
    table.getByRole("cell", { name: "00125" }).first(),
  ).toBeVisible();
  await expect(table.getByText("nulo")).toHaveCount(1);
  await page.getByLabel("Buscar en los registros").fill("este");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await expect(page.getByText("1 registros contienen «este».")).toBeVisible();
  await expect(table.getByRole("row")).toHaveCount(2);

  // Columnas: estadísticas que tienen sentido para cada variable.
  await page.getByRole("tab", { name: "Columnas" }).click();
  await page.getByRole("button", { name: /^precio/ }).click();
  const precio = page.getByRole("region", { name: "Columna precio" });
  await expect(precio).toContainText("Cuantitativa continua");
  await expect(precio.getByLabel("Estadísticas numéricas")).toContainText(
    "Mediana10,5",
  );
  await page.getByRole("button", { name: /^codigo/ }).click();
  await expect(
    page.getByRole("region", { name: "Columna codigo" }),
  ).toContainText("se conservan como texto");

  // Calidad: diagnóstico sin correcciones automáticas.
  await page.getByRole("tab", { name: "Calidad" }).click();
  const findings = page.getByLabel("Incidencias de calidad");
  await expect(findings).toContainText("Filas duplicadas");
  await expect(findings).toContainText(
    "Posibles faltantes escritos como texto en «estado»",
  );

  // Archivo: cómo se leyó.
  await page.getByRole("tab", { name: "Archivo" }).click();
  await expect(page.getByLabel("Lectura del original")).toContainText("UTF-8");

  // Diccionario: una corrección manual se confirma y persiste tras recargar.
  await page.getByRole("tab", { name: "Diccionario" }).click();
  await page
    .getByRole("button", { name: "Editar la clasificación de unidades" })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Rol analítico").selectOption("dimension");
  await dialog.getByLabel("Naturaleza estadística").selectOption("ordinal");
  await dialog.getByLabel("Observación").fill("Escala de 1 a 5");
  await dialog.getByRole("button", { name: "Guardar corrección" }).click();
  await expect(
    page.getByText("Corrección de «unidades» guardada", { exact: false }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("tab", { name: "Diccionario" }).click();
  const row = page.getByRole("row", { name: /unidades/ });
  await expect(row).toContainText("Cualitativa ordinal", { timeout: 30000 });
  await expect(row).toContainText("Corrección manual");
  await expect(row).toContainText("Escala de 1 a 5");
});
