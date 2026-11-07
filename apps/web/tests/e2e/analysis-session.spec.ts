import { expect, test, type Page } from "@playwright/test";
import { openAdvanced } from "./workspace-support";

// Fase 11A: una sola fuente activa por proyecto; una carga inválida no la sustituye.
test.beforeEach(async ({ page }) => {
  const result = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista sesión",
      email: `session-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-sesion-123",
    },
  });
  expect(result.status()).toBe(201);
});

async function uploadVersion(page: Page, name: string, content: string) {
  await page
    .getByRole("button", { name: "Subir nueva versión", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Archivo CSV")
    .setInputFiles({
      name,
      mimeType: "text/csv",
      buffer: Buffer.from(content),
    });
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Subir y analizar CSV" })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

async function useAsActive(page: Page, number: number) {
  await page
    .getByRole("button", { name: `Usar v${number} como fuente activa` })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Usar como fuente activa" })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

test("fuente activa: una carga inválida no sustituye a la activa", async ({
  page,
}) => {
  await page.goto("/new");
  await page.getByLabel("Nombre del proyecto").fill("Fuente única");
  await page.locator('input[type="file"]').setInputFiles({
    name: "ventas_a.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("id,importe\n001,10\n"),
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await openAdvanced(page);
  await expect(
    page.getByRole("heading", { name: "Vista previa del CSV", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  const active = page.getByTestId("active-source");
  await expect(active).toHaveText("ninguna");
  await useAsActive(page, 1);
  await expect(active).toHaveText("v1 · ventas_a.csv");
  await expect(page.getByText("Es la que estás viendo")).toBeVisible();

  // B no se puede procesar: no ofrece sustituir y la activa sigue siendo A.
  await uploadVersion(page, "ventas_b.csv", "id,importe\n1\n");
  await expect(
    page.getByRole("heading", { name: "No se pudo procesar este CSV" }),
  ).toBeVisible({ timeout: 20000 });
  await expect(active).toHaveText("v1 · ventas_a.csv");
  await expect(
    page.getByRole("button", { name: "Usar v2 como fuente activa" }),
  ).toHaveCount(0);

  // C es válida: se sustituye de forma explícita y queda en el historial.
  await uploadVersion(page, "ventas_c.csv", "id,importe\n002,20\n");
  await expect(
    page.getByRole("heading", { name: "Vista previa del CSV", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  await useAsActive(page, 3);
  await expect(active).toHaveText("v3 · ventas_c.csv");
  await page.getByRole("button", { name: "Historial (2)" }).click();
  const history = page.getByRole("list", { name: "Historial de fuentes" });
  await expect(history.getByRole("listitem")).toHaveCount(2);

  await page.reload();
  await openAdvanced(page);
  await expect(page.getByTestId("active-source")).toHaveText(
    "v3 · ventas_c.csv",
  );
});
