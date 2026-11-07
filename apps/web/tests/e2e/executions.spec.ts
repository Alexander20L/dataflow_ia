import { expect, test } from "@playwright/test";
import { openAdvanced } from "./workspace-support";

test("dos revisiones de un plan sobre una tabla conservan el baseline y sus resultados independientes", async ({
  page,
}) => {
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista",
      email: `execution-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-12345",
    },
  });
  expect(registered.status()).toBe(201);
  await page.goto("/new");
  await page
    .getByLabel("Nombre del proyecto")
    .fill("Ejecuciones independientes CSV");
  const content = Buffer.from("id,importe\n001,10\n002,\n001,10\n");
  await page
    .locator('input[type="file"]')
    .setInputFiles({ name: "test.csv", mimeType: "text/csv", buffer: content });
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
  const panel = page.getByRole("region", {
    name: "Ejecuciones independientes",
    exact: true,
  });
  const select = panel.getByLabel("Ejecución", { exact: true });
  await expect(select).not.toHaveValue("");
  const baselineRun = await select.inputValue();
  // Revisión 1: sólo calidad.
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
  const execute = panel.getByRole("button", {
    name: "Ejecutar plan",
    exact: true,
  });
  await execute.click();
  await expect(select).not.toHaveValue(baselineRun);
  const qualityRun = await select.inputValue();
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(`/api/v1/executions/${qualityRun}`)
          ).json()
        ).state,
      { timeout: 20000 },
    )
    .toBe("succeeded");
  await expect(panel.getByText("Completada", { exact: true })).toBeVisible();
  await expect(
    panel.getByRole("heading", { name: "Calidad de esta ejecución" }),
  ).toBeVisible();
  // Revisión 2: perfil y calidad, sin alterar la ejecución anterior.
  await panel
    .getByRole("button", { name: "Añadir Perfil de columnas", exact: true })
    .click();
  await panel
    .getByRole("button", { name: "Guardar plan", exact: true })
    .click();
  await expect(
    summary.getByRole("heading", { name: "Revisión 2" }),
  ).toBeVisible();
  await execute.click();
  await expect(select).not.toHaveValue(qualityRun);
  const profileRun = await select.inputValue();
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(`/api/v1/executions/${profileRun}`)
          ).json()
        ).state,
      { timeout: 20000 },
    )
    .toBe("succeeded");
  const first = await (
    await page.request.get(`/api/v1/executions/${qualityRun}/artifacts`)
  ).json();
  const second = await (
    await page.request.get(`/api/v1/executions/${profileRun}/artifacts`)
  ).json();
  expect(first.map((a: { kind: string }) => a.kind)).toEqual(["quality"]);
  expect(second.map((a: { kind: string }) => a.kind).sort()).toEqual([
    "profile",
    "quality",
  ]);
  expect(
    await (
      await page.request.get(`/api/v1/versions/${version}/diagnostic`)
    ).json(),
  ).toEqual(baseline);
  expect(
    await (
      await page.request.get(`/api/v1/versions/${version}/original`)
    ).body(),
  ).toEqual(content);
  await panel
    .getByText("Ver plan y configuración fijados", { exact: true })
    .click();
  await expect(panel.locator("pre")).toContainText("understanding.profile");
  await expect(
    panel.getByText("#1 · succeeded", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await openAdvanced(page);
  await expect(page.getByLabel("Versión", { exact: true })).toHaveValue(
    version,
  );
  await expect(
    page
      .getByRole("region", { name: "Ejecuciones independientes" })
      .getByLabel("Ejecución", { exact: true })
      .locator("option"),
  ).toHaveCount(4); // Baseline, explicación automática y dos ejecuciones del plan.
  await expect(
    panel.getByRole("option", { name: /Explicación automática IA/ }),
  ).toHaveCount(1);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false);
});
