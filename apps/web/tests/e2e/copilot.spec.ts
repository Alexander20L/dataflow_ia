import { expect, test } from "@playwright/test";
import { openAdvanced } from "./workspace-support";
import { csv, typedVersion } from "./analytics-support";

test("copiloto: petición → aclaración → métrica → consulta → explicación con cifras verificadas", async ({
  page,
}) => {
  // Incluye la preparación de v2 (limpieza y diagnóstico) por la API.
  test.setTimeout(150_000);
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Copiloto",
      email: `copilot-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-12345",
    },
  });
  expect(registered.status()).toBe(201);
  await page.goto("/new");
  await page.getByLabel("Nombre del proyecto").fill("Ventas con copiloto");
  await page.locator('input[type="file"]').setInputFiles({
    name: "ventas_calidad.csv",
    mimeType: "text/csv",
    buffer: csv,
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await openAdvanced(page);
  await expect(
    page.getByRole("heading", { name: "Vista previa del CSV", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  await typedVersion(page);
  await page.reload();
  await openAdvanced(page);
  await expect(
    page.getByRole("status", { name: "Versión que estás viendo" }),
  ).toContainText("Estás viendo v2", { timeout: 20000 });

  const copilot = page.getByRole("region", { name: "Copiloto de análisis" });
  const conversation = copilot.getByRole("list", {
    name: "Conversación con el copiloto",
  });
  const request = "Compara las ventas mensuales por región";
  async function ask() {
    await copilot.getByLabel("Pregunta al copiloto").fill(request);
    await copilot.getByRole("button", { name: "Enviar" }).click();
  }

  // 1. Sin fecha de negocio confirmada, el copiloto pregunta antes de proponer.
  await ask();
  const question = conversation.getByRole("group", {
    name: "Pregunta del copiloto",
  });
  await expect(question).toContainText("Falta confirmar la fecha de negocio");
  await question.getByRole("button", { name: "Ir a Entendimiento" }).click();

  // 2. La persona confirma la semántica (no el copiloto).
  const editor = page.getByRole("region", {
    name: "Revisión semántica",
    exact: true,
  });
  await editor
    .getByLabel("Rol de importe", { exact: true })
    .selectOption("measure");
  await editor
    .getByRole("button", { name: "Detalles de importe", exact: true })
    .click();
  await page.getByRole("dialog").getByLabel("Moneda ISO 4217").fill("EUR");
  await page.getByRole("button", { name: "Aplicar al borrador" }).click();
  await editor
    .getByLabel("Revisión de importe", { exact: true })
    .selectOption("confirmed");
  await editor
    .getByLabel("Rol de fecha", { exact: true })
    .selectOption("business_date");
  await editor
    .getByLabel("Revisión de fecha", { exact: true })
    .selectOption("confirmed");
  await editor
    .getByRole("button", { name: "Guardar revisión semántica" })
    .click();
  await expect(
    editor.getByText("Revisión 1 guardada", { exact: true }),
  ).toBeVisible();

  // 3. Sin métrica: propone el borrador y sólo se crea al pulsar el botón.
  await ask();
  const metric = conversation.getByRole("group", {
    name: "Métrica propuesta",
  });
  await expect(metric).toContainText("Suma de importe");
  await expect(metric).toContainText("Validada con el catálogo");
  await metric.getByRole("button", { name: "Crear métrica" }).click();
  await expect(metric.getByRole("status")).toContainText("Métrica creada");

  // 4. Con la métrica: consulta validada por planning que corre al confirmarla.
  await ask();
  const proposal = conversation.getByRole("group", {
    name: "Consulta propuesta",
  });
  await expect(proposal).toContainText("Ventas");
  await expect(proposal).toContainText("region · Mes");
  await expect(proposal).toContainText("Validada con el catálogo");
  await proposal.getByRole("button", { name: "Ejecutar consulta" }).click();
  await expect(proposal.getByText("Consulta calculada")).toBeVisible({
    timeout: 30000,
  });

  // 5. Explicación: las cifras salen de la evidencia y abren su procedencia.
  await proposal.getByRole("button", { name: "Explicar resultado" }).click();
  const highest = conversation.getByRole("button", {
    name: "De dónde sale 201,00 EUR",
  });
  await expect(highest).toBeVisible({ timeout: 20000 });
  await expect(
    conversation.getByRole("button", { name: "De dónde sale 80,00 EUR" }),
  ).toBeVisible();
  await expect(conversation).toContainText("Norte, 2026-01");
  await expect(conversation.locator(".copilot-unverified")).toHaveCount(0);
  await highest.click();
  const provenance = page.getByRole("dialog", {
    name: "De dónde sale este número",
  });
  await expect(provenance.getByTestId("evidence-value")).toHaveText(
    "201.00 EUR",
  );
  await expect(provenance).toContainText("Norte · 2026-01");
  await provenance
    .getByRole("button", { name: /cerrar/i })
    .first()
    .click();

  // La conversación queda guardada.
  await page.reload();
  await openAdvanced(page);
  await expect(
    page
      .getByRole("region", { name: "Copiloto de análisis" })
      .getByRole("button", { name: "De dónde sale 201,00 EUR" }),
  ).toBeVisible({ timeout: 20000 });

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false);
});

test("copiloto: un plan de limpieza propuesto sigue la vista previa y la aprobación de la Fase 5", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Copiloto limpieza",
      email: `copilot-cleaning-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-12345",
    },
  });
  expect(registered.status()).toBe(201);
  await page.goto("/new");
  await page.getByLabel("Nombre del proyecto").fill("Limpieza con copiloto");
  await page.locator('input[type="file"]').setInputFiles({
    name: "ventas_calidad.csv",
    mimeType: "text/csv",
    buffer: csv,
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await openAdvanced(page);
  await expect(
    page.getByRole("heading", { name: "Vista previa del CSV", exact: true }),
  ).toBeVisible({ timeout: 20000 });

  const copilot = page.getByRole("region", { name: "Copiloto de análisis" });
  await copilot
    .getByLabel("Pregunta al copiloto")
    .fill("Limpia los espacios de las columnas de texto");
  await copilot.getByRole("button", { name: "Enviar" }).click();
  const card = copilot.getByRole("group", {
    name: "Plan de limpieza propuesto",
  });
  await expect(card).toContainText("Recortar espacios de los bordes");
  await expect(card).toContainText("Validada con el catálogo");
  await card.getByRole("button", { name: "Abrir plan de limpieza" }).click();

  // Abrirlo sólo guarda el plan: la vista previa y la aprobación siguen en Limpieza.
  const stage = page.getByRole("region", { name: "Limpieza supervisada" });
  await expect(
    stage.getByRole("heading", {
      name: "Plan de limpieza propuesto por el copiloto",
    }),
  ).toBeVisible();
  await stage.getByRole("button", { name: "Generar vista previa" }).click();
  const effect = stage.getByRole("region", { name: "Vista previa del efecto" });
  await expect(
    effect.getByRole("button", { name: "Aprobar efecto…" }),
  ).toBeVisible({ timeout: 20000 });
  await expect(
    page.getByRole("status", { name: "Versión que estás viendo" }),
  ).toContainText("Estás viendo v1");
});
