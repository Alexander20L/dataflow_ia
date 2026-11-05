import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const csv = readFileSync(
  path.resolve(__dirname, "../../../../examples/ventas_calidad.csv"),
);

test("reglas de calidad del usuario: revisión inmutable y diagnóstico separado de la completitud técnica", async ({
  page,
}) => {
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Reglas",
      email: `rules-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-12345",
    },
  });
  expect(registered.status()).toBe(201);
  await page.goto("/new");
  await page.getByLabel("Nombre del proyecto").fill("Reglas de ventas");
  await page.locator('input[type="file"]').setInputFiles({
    name: "ventas_calidad.csv",
    mimeType: "text/csv",
    buffer: csv,
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await expect(
    page.getByRole("heading", { name: "Vista previa del CSV", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  const stages = page.getByRole("navigation", { name: "Etapas del CSV real" });
  await stages.getByRole("button", { name: "Calidad", exact: false }).click();

  const rules = page.getByRole("region", { name: "Reglas de calidad" });
  const kind = rules.getByLabel("Tipo de regla");
  const column = rules.getByLabel("Columna de la regla");
  const add = rules.getByRole("button", { name: "Añadir regla" });

  // Un rango sólo admite columnas tipadas: en v1 (todo texto) no hay ninguna.
  await kind.selectOption("range");
  await expect(column.locator("option")).toHaveCount(1);

  await kind.selectOption("required");
  await column.selectOption({ label: "importe · string" });
  await add.click();
  await kind.selectOption("allowed_values");
  await column.selectOption({ label: "region · string" });
  await rules.getByLabel("Valores permitidos").fill("Norte, Sur, Este");
  await add.click();
  await kind.selectOption("unique_key");
  await rules.getByLabel("Columna de la clave: id", { exact: true }).check();
  await rules.getByLabel("Gravedad").selectOption("high");
  await add.click();
  await expect(
    rules
      .getByRole("table", { name: "Reglas del conjunto" })
      .locator("tbody tr"),
  ).toHaveCount(3);
  await expect(rules.getByText("Cambios sin guardar")).toBeVisible();
  await expect(
    rules.getByRole("button", { name: "Evaluar reglas" }),
  ).toBeDisabled();

  // Salir de la etapa con reglas sin guardar pide confirmación.
  await stages.getByRole("button", { name: "Limpieza", exact: false }).click();
  const unsaved = page.getByRole("dialog", {
    name: "Hay cambios sin guardar en las reglas de calidad",
  });
  await unsaved.getByRole("button", { name: "Seguir editando" }).click();
  await expect(unsaved).toBeHidden();

  await rules.getByRole("button", { name: "Guardar reglas" }).click();
  await expect(rules.getByText("Revisión 1", { exact: true })).toBeVisible();
  await rules.getByRole("button", { name: "Evaluar reglas" }).click();

  const business = rules.getByRole("region", { name: "Reglas de negocio" });
  await expect(business).toContainText("3 de 3 con incidencias", {
    timeout: 30000,
  });
  await expect(business.getByTestId("violations-required_importe")).toHaveText(
    "1",
  );
  await expect(
    business.getByTestId("violations-allowed_values_region"),
  ).toHaveText("1");
  await expect(business.getByTestId("violations-unique_key_id")).toHaveText(
    "1",
  );
  // La completitud técnica no cambia por las reglas de negocio.
  await expect(
    rules
      .getByRole("region", { name: "Calidad técnica" })
      .getByTestId("technical-completeness"),
  ).toHaveText("96,67 %");
  await expect(
    page
      .locator(".mini-metrics > div")
      .filter({ hasText: "Completitud de celdas" })
      .first(),
  ).toContainText("96,67 %");

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false);
});
