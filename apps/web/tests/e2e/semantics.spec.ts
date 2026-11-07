import { expect, test, type Page } from "@playwright/test";
import { openAdvanced } from "./workspace-support";

const csv = Buffer.from(
  "id,fecha,region,importe\n001,2026-01-01,Norte,10.50\n002,2026-01-02,Sur,\n001,2026-01-01,Norte,10.50\n",
);
async function prepare(page: Page) {
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Semántica",
      email: `semantic-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-12345",
    },
  });
  expect(registered.status()).toBe(201);
  await page.goto("/new");
  await page
    .getByLabel("Nombre del proyecto")
    .fill("Revisión semántica de ventas");
  await page
    .locator('input[type="file"]')
    .setInputFiles({ name: "semantic.csv", mimeType: "text/csv", buffer: csv });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await openAdvanced(page);
  await expect(
    page.getByRole("heading", { name: "Vista previa del CSV", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  const version = await page
    .getByLabel("Versión", { exact: true })
    .inputValue();
  const baseline = await (
    await page.request.get(`/api/v1/versions/${version}/diagnostic`)
  ).json();
  await page
    .getByRole("navigation", { name: "Etapas del CSV real" })
    .getByRole("button", { name: "Entendimiento", exact: false })
    .click();
  await expect(
    page.getByRole("heading", { name: "Revisión semántica de tus datos" }),
  ).toBeVisible();
  return { version, baseline };
}

test("guardar contexto, consultar revisiones y fijar una revisión histórica a un plan", async ({
  page,
}) => {
  const { version, baseline } = await prepare(page);
  const editor = page.getByRole("region", {
    name: "Revisión semántica",
    exact: true,
  });
  await editor.getByLabel("Descripción del dataset").fill("Ventas iniciales");
  await editor
    .getByLabel("¿Qué representa cada fila?")
    .fill("Una operación de venta");
  await editor
    .getByLabel("Revisión del significado de cada fila")
    .selectOption("confirmed");
  await editor
    .getByLabel("Rol de id", { exact: true })
    .selectOption("identifier");
  await editor
    .getByLabel("Revisión de id", { exact: true })
    .selectOption("confirmed");
  await editor
    .getByRole("button", { name: "Detalles de importe", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Descripción", { exact: true })
    .fill("Importe de la operación");
  await page.getByRole("dialog").getByLabel("Moneda ISO 4217").fill("EUR");
  await page.getByRole("button", { name: "Aplicar al borrador" }).click();
  await editor
    .getByLabel("Revisión de importe", { exact: true })
    .selectOption("confirmed");
  await editor.getByLabel("Clave: id", { exact: true }).check();
  await editor.getByLabel("Revisión de la clave").selectOption("confirmed");
  await editor
    .getByRole("button", { name: "Guardar revisión semántica" })
    .click();
  await expect(
    editor.getByText("Revisión 1 guardada", { exact: true }),
  ).toBeVisible();
  await expect(
    editor.getByText("La clave tiene 1 repeticiones.", { exact: false }),
  ).toBeVisible();
  await page.reload();
  await openAdvanced(page);
  await page
    .getByRole("navigation", { name: "Etapas del CSV real" })
    .getByRole("button", { name: "Entendimiento", exact: false })
    .click();
  await expect(editor.getByLabel("Descripción del dataset")).toHaveValue(
    "Ventas iniciales",
  );
  await expect(
    editor.getByLabel("Revisión de id", { exact: true }),
  ).toHaveValue("confirmed");
  await editor.getByLabel("Descripción del dataset").fill("Ventas corregidas");
  await editor
    .getByRole("button", { name: "Guardar revisión semántica" })
    .click();
  await expect(
    editor.getByText("Revisión 2 guardada", { exact: true }),
  ).toBeVisible();
  await editor.getByRole("button", { name: "Historial semántico" }).click();
  const history = page.getByRole("dialog", { name: "Historial semántico" });
  const first = history.getByRole("option", {
    name: "Revisión 1",
    exact: true,
  });
  const firstId = await first.getAttribute("value");
  await history.getByLabel("Revisión guardada").selectOption(firstId!);
  await expect(
    history.getByText("Ventas iniciales", { exact: true }),
  ).toBeVisible();
  await expect(
    history.getByText("Diferencias respecto a la revisión actual:"),
  ).toBeVisible();
  await history.getByRole("button", { name: "Cerrar diálogo" }).click();
  const panel = page.getByRole("region", {
    name: "Ejecuciones independientes",
    exact: true,
  });
  await panel
    .getByLabel("Revisión semántica (opcional)")
    .selectOption(firstId!);
  await panel
    .getByRole("button", { name: "Añadir Evaluar calidad", exact: true })
    .click();
  await panel
    .getByRole("button", { name: "Guardar plan", exact: true })
    .click();
  const summary = panel.getByRole("region", { name: "Resumen del plan" });
  await expect(summary.getByTestId("plan-status")).toHaveText(
    "Válido · listo para ejecutar",
  );
  await expect(summary).toContainText("Revisión 1 · SHA");
  const oldRun = await panel
    .getByLabel("Ejecución", { exact: true })
    .inputValue();
  await panel
    .getByRole("button", { name: "Ejecutar plan", exact: true })
    .click();
  await expect(panel.getByLabel("Ejecución", { exact: true })).not.toHaveValue(
    oldRun,
  );
  const run = await panel.getByLabel("Ejecución", { exact: true }).inputValue();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/v1/executions/${run}`)).json())
          .state,
      { timeout: 20000 },
    )
    .toBe("succeeded");
  const detail = await (
    await page.request.get(`/api/v1/executions/${run}`)
  ).json();
  expect(detail.plan.content.semantic_ref.id).toBe(firstId);
  expect(detail.plan.content.semantic_ref.revision).toBe(1);
  expect(
    await (
      await page.request.get(`/api/v1/versions/${version}/diagnostic`)
    ).json(),
  ).toEqual(baseline);
  expect(
    await (
      await page.request.get(`/api/v1/versions/${version}/original`)
    ).body(),
  ).toEqual(csv);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false);
});

test("un conflicto conserva el borrador y cambiar de etapa exige descartar explícitamente", async ({
  page,
}) => {
  const { version } = await prepare(page);
  const editor = page.getByRole("region", {
    name: "Revisión semántica",
    exact: true,
  });
  await editor.getByLabel("Descripción del dataset").fill("Primera revisión");
  await editor
    .getByRole("button", { name: "Guardar revisión semántica" })
    .click();
  await expect(
    editor.getByText("Revisión 1 guardada", { exact: true }),
  ).toBeVisible();
  await editor.getByLabel("Descripción del dataset").fill("Borrador local");
  const table = (
    await (
      await page.request.get(`/api/v1/versions/${version}/representations`)
    ).json()
  )[0];
  const context = await (
    await page.request.get(`/api/v1/representations/${table.id}/understanding`)
  ).json();
  const session = await (await page.request.get("/api/v1/auth/me")).json();
  const current = await page.request.post(
    `/api/v1/representations/${table.id}/semantic-contracts`,
    {
      headers: {
        Origin: "http://127.0.0.1:3100",
        "x-csrf-token": session.csrf_token,
        "Idempotency-Key": crypto.randomUUID(),
      },
      data: {
        table_sha256: table.sha256,
        expected_revision: 1,
        draft: {
          ...context.editable,
          dataset_description: "Versión del servidor",
        },
      },
    },
  );
  expect(current.status()).toBe(200);
  await editor
    .getByRole("button", { name: "Guardar revisión semántica" })
    .click();
  await expect(
    editor.getByText("El servidor tiene la revisión 2", { exact: false }),
  ).toBeVisible();
  await expect(editor.getByLabel("Descripción del dataset")).toHaveValue(
    "Borrador local",
  );
  await editor.getByRole("button", { name: "Cargar revisión actual" }).click();
  await page.getByRole("button", { name: "Descartar y cargar" }).click();
  await expect(editor.getByLabel("Descripción del dataset")).toHaveValue(
    "Versión del servidor",
  );
  await editor
    .getByLabel("Descripción del dataset")
    .fill("Cambios no guardados");
  await page
    .getByRole("navigation", { name: "Etapas del CSV real" })
    .getByRole("button", { name: "Calidad", exact: false })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Hay cambios semánticos sin guardar" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Seguir editando", exact: true })
    .click();
  await expect(editor.getByLabel("Descripción del dataset")).toHaveValue(
    "Cambios no guardados",
  );
  await page
    .getByRole("navigation", { name: "Etapas del CSV real" })
    .getByRole("button", { name: "Calidad", exact: false })
    .click();
  await page.getByRole("button", { name: "Descartar y continuar" }).click();
  await expect(
    page.getByRole("heading", { name: "Calidad", exact: true }),
  ).toBeVisible();
  expect(
    (
      await (
        await page.request.get(
          `/api/v1/representations/${table.id}/understanding`,
        )
      ).json()
    ).head.revision,
  ).toBe(2);
});
