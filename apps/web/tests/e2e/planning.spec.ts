import { expect, test, type Page } from "@playwright/test";

const csv = Buffer.from("id,importe\n001,10\n002,\n001,10\n");
const origin = { Origin: "http://127.0.0.1:3100" };

async function state(page: Page, run: string) {
  return (await (await page.request.get(`/api/v1/executions/${run}`)).json())
    .state;
}

test("crear un plan, ver su requisito pendiente, corregirlo y ejecutarlo sobre la tabla fijada", async ({
  page,
}) => {
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: origin,
    data: {
      name: "Planificación",
      email: `planning-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-12345",
    },
  });
  expect(registered.status()).toBe(201);
  await page.goto("/new");
  await page.getByLabel("Nombre del proyecto").fill("Planes sobre ventas");
  await page
    .locator('input[type="file"]')
    .setInputFiles({ name: "ventas.csv", mimeType: "text/csv", buffer: csv });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await expect(
    page.getByRole("heading", { name: "Vista previa del CSV", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  const version = await page
    .getByLabel("Versión", { exact: true })
    .inputValue();
  const table = (
    await (
      await page.request.get(`/api/v1/versions/${version}/representations`)
    ).json()
  )[0];
  const panel = page.getByRole("region", {
    name: "Ejecuciones independientes",
    exact: true,
  });
  const planSelect = panel.getByLabel("Plan", { exact: true });
  await expect(planSelect).toHaveValue("new");
  await expect(panel.getByLabel("Tabla de entrada fijada")).toHaveValue(
    table.id,
  );
  // La lectura de CSV pertenece al original: no se ofrece sobre una tabla.
  await expect(
    panel.getByRole("button", { name: "Añadir Leer CSV", exact: true }),
  ).toBeDisabled();

  // 1. Un plan vacío se guarda, muestra qué le falta y no se puede ejecutar.
  await panel
    .getByRole("button", { name: "Guardar plan", exact: true })
    .click();
  const summary = panel.getByRole("region", { name: "Resumen del plan" });
  await expect(summary.getByTestId("plan-status")).toHaveText(
    "Incompleto · 1 pendiente(s)",
  );
  const problems = summary.getByRole("list", { name: "Problemas pendientes" });
  await expect(problems).toContainText("Plan vacío");
  await expect(problems).toContainText("EMPTY_PLAN");
  await expect(summary.getByTestId("plan-input-sha")).toHaveText(
    `SHA-256 ${table.sha256}`,
  );
  const execute = panel.getByRole("button", {
    name: "Ejecutar plan",
    exact: true,
  });
  await expect(execute).toBeDisabled();

  // 2. El enlace del problema lleva a donde se resuelve.
  await summary
    .getByRole("button", { name: "Ir al catálogo de operaciones" })
    .click();
  await expect(panel.locator("#plan-catalog")).toBeFocused();
  await panel
    .getByRole("button", { name: "Añadir Evaluar calidad", exact: true })
    .click();
  const step = panel.getByRole("listitem", { name: "Paso evaluate" });
  await expect(step).toBeVisible();
  await expect(step.getByText("csv-quality-v1")).toBeVisible();
  await expect(
    panel.getByText("Cambios sin guardar", { exact: true }),
  ).toBeVisible();
  await expect(execute).toBeDisabled();

  // 3. Cambiar de plan con un borrador exige confirmación y lo conserva.
  await planSelect.selectOption("new");
  const discard = page.getByRole("dialog", {
    name: "Hay cambios sin guardar en el plan",
  });
  await expect(discard).toBeVisible();
  await discard.getByRole("button", { name: "Seguir editando" }).click();
  await expect(step).toBeVisible();

  // 4. Guardar crea la revisión 2, ya válida.
  await panel
    .getByRole("button", { name: "Guardar plan", exact: true })
    .click();
  await expect(summary.getByTestId("plan-status")).toHaveText(
    "Válido · listo para ejecutar",
  );
  await expect(
    summary.getByRole("heading", { name: "Revisión 2" }),
  ).toBeVisible();
  await expect(
    panel.getByText("Cambios sin guardar", { exact: true }),
  ).toHaveCount(0);
  const runs = panel.getByLabel("Ejecución", { exact: true });
  const baselineRun = await runs.inputValue();
  await execute.click();
  await expect(runs).not.toHaveValue(baselineRun);
  const run = await runs.inputValue();
  await expect
    .poll(() => state(page, run), { timeout: 20000 })
    .toBe("succeeded");
  const detail = await (
    await page.request.get(`/api/v1/executions/${run}`)
  ).json();
  expect(detail.kind).toBe("plan");
  expect(detail.plan.revision).toBe(2);
  expect(detail.input_artifact_id).toBe(table.id);
  const artifacts = await (
    await page.request.get(`/api/v1/executions/${run}/artifacts`)
  ).json();
  expect(artifacts.map((a: { kind: string }) => a.kind)).toEqual(["quality"]);
  await expect(
    panel.getByRole("heading", { name: "Calidad de esta ejecución" }),
  ).toBeVisible();

  // 5. Recargar conserva la revisión guardada.
  await page.reload();
  await expect(planSelect).toContainText("revisión 2 · válido");
  await expect(summary.getByTestId("plan-input-sha")).toHaveText(
    `SHA-256 ${table.sha256}`,
  );

  // 6. Una nueva carga cambia la versión predeterminada; el plan conserva su tabla.
  const project = (await (await page.request.get("/api/v1/projects")).json())
    .items[0];
  const session = await (await page.request.get("/api/v1/auth/me")).json();
  const newer = await page.request.post(
    `/api/v1/projects/${project.id}/imports?file_name=ventas-v2.csv`,
    {
      headers: {
        ...origin,
        "x-csrf-token": session.csrf_token,
        "Idempotency-Key": crypto.randomUUID(),
        "Content-Type": "text/csv",
      },
      data: Buffer.from("id,importe\n001,10\n003,7\n"),
    },
  );
  expect(newer.status()).toBe(202);
  const newerVersion = await newer.json();
  await expect
    .poll(() => state(page, newerVersion.execution_id), { timeout: 20000 })
    .toBe("succeeded");
  await page.reload();
  await expect(page.getByLabel("Versión", { exact: true })).toHaveValue(
    newerVersion.id,
  );
  await page.getByLabel("Versión", { exact: true }).selectOption(version);
  await expect(planSelect).toContainText("revisión 2 · válido");
  const previous = await runs.inputValue();
  await execute.click();
  await expect(runs).not.toHaveValue(previous);
  const again = await runs.inputValue();
  await expect
    .poll(() => state(page, again), { timeout: 20000 })
    .toBe("succeeded");
  const pinned = await (
    await page.request.get(`/api/v1/executions/${again}`)
  ).json();
  expect(pinned.version_id).toBe(version);
  expect(pinned.input_artifact_id).toBe(table.id);
  expect(pinned.input_artifact_sha256).toBe(table.sha256);

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false);
});
