import { readFile } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";

// Fase 27: pestaña Informe. Vista previa con las secciones del documento, revisión humana de
// los hallazgos, versión nueva con la selección e historial que conserva la anterior.
test("Informe: vista previa, revisión, versión nueva e historial", async ({
  page,
}) => {
  test.setTimeout(150_000);
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista Informe",
      email: `informe-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-Informe-123",
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
    .getByRole("tab", { name: "Informe", exact: true })
    .click({ timeout: 30000 });
  const tab = page.getByRole("region", { name: "Informe", exact: true });

  // Vista previa: las secciones de la especificación, en orden.
  const preview = tab.getByRole("article", {
    name: "Vista previa del informe",
  });
  await expect(preview).toBeVisible({ timeout: 90000 });
  for (const name of [
    "Resumen ejecutivo",
    "Descripción del dataset",
    "Calidad de los datos y metodología",
    "Hallazgos principales",
    "Investigaciones realizadas",
    "Conclusiones y recomendaciones",
  ])
    await expect(
      preview.getByRole("region", { name, exact: true }),
    ).toBeVisible();
  await expect(tab).toContainText("Versión 1 del informe");
  await expect(
    tab.getByRole("link", { name: "Descargar PDF" }),
  ).toHaveAttribute("href", /report\.pdf$/);

  // Revisión: aprobar un hallazgo y generar una versión nueva con esa selección.
  await tab.getByRole("tab", { name: "Revisión de hallazgos" }).click();
  const generate = tab.getByRole("button", {
    name: "Generar versión con mi selección",
  });
  await expect(generate).toBeDisabled();
  const candidates = tab.getByRole("list", { name: "Hallazgos candidatos" });
  const candidate = candidates.getByRole("listitem").last();
  await candidate.getByRole("button", { name: "Aprobar" }).click();
  await expect(candidate).toContainText("Aprobado");
  await expect(candidate).toContainText("Principal");
  await generate.click();
  await expect(
    tab.getByText(/Se está generando la versión nueva/),
  ).toBeVisible();

  // Historial: dos versiones; la primera se puede volver a ver.
  await tab.getByRole("tab", { name: "Historial" }).click();
  const history = tab.getByRole("table", { name: "Versiones del informe" });
  await expect(history.getByRole("row")).toHaveCount(3, { timeout: 60000 });
  await expect(history).toContainText("Con tu selección");
  await expect(history.getByRole("button", { name: "Ver" })).toHaveCount(2, {
    timeout: 60000,
  });
  await history.getByRole("button", { name: "Ver" }).last().click();
  await expect(tab).toContainText("Estás viendo una versión anterior");
  await expect(tab).toContainText("Versión 1 del informe");
  await tab.getByRole("button", { name: "Volver a la actual" }).click();
  await expect(tab).toContainText("Versión 2 del informe");
});
