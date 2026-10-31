import { expect, test } from "@playwright/test";

test("registro, persistencia real, edición, archivo y aislamiento al cambiar de cuenta", async ({
  page,
}) => {
  const ownerEmail = `owner-${crypto.randomUUID()}@example.com`;
  const password = "Una-contraseña-de-prueba-123";
  await page.goto("/");
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await page.getByLabel("Nombre", { exact: true }).fill("Carolina");
  await page.getByLabel("Correo electrónico").fill(ownerEmail);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Hola, Carolina" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Nuevo análisis", exact: true }).click();
  await page
    .getByLabel("Nombre del proyecto")
    .fill("Proyecto persistente de Carolina");
  await page
    .getByLabel("Descripción (opcional)")
    .fill("Descripción guardada en PostgreSQL");
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await expect(
    page.getByRole("heading", { name: "Proyecto persistente de Carolina" }),
  ).toBeVisible();
  const projectPath = new URL(page.url()).pathname;
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Proyecto persistente de Carolina" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Editar proyecto" }).click();
  await page
    .getByRole("dialog")
    .getByLabel("Nombre del proyecto")
    .fill("Proyecto editado de Carolina");
  await page.getByRole("button", { name: "Guardar cambios" }).click();
  await expect(
    page.getByRole("heading", { name: "Proyecto editado de Carolina" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Archivar", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar archivo" }).click();
  await expect(page.getByText("Archivado · revisión 3")).toBeVisible();
  await page.goto("/settings");
  await page
    .getByRole("button", { name: "Cerrar sesión", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Bienvenido de nuevo" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await page.getByLabel("Nombre", { exact: true }).fill("Gabriel");
  await page
    .getByLabel("Correo electrónico")
    .fill(`other-${crypto.randomUUID()}@example.com`);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Cerrar sesión", exact: true }),
  ).toBeVisible();
  await page.goto(projectPath);
  await expect(
    page.getByRole("heading", { name: "No se pudo abrir el proyecto" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Proyecto editado de Carolina" }),
  ).toHaveCount(0);
  await page.goto("/projects");
  await expect(
    page.getByText("Tu próximo proyecto empieza aquí"),
  ).toBeVisible();
  await page.goto("/settings");
  await page
    .getByRole("button", { name: "Cerrar sesión", exact: true })
    .click();
  await page.getByLabel("Correo electrónico").fill(ownerEmail);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Iniciar sesión", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Cerrar sesión", exact: true }),
  ).toBeVisible();
  await page.goto("/projects");
  await page.getByLabel("Filtrar estado").selectOption("archived");
  await expect(
    page.getByRole("link", {
      name: "Abrir Proyecto editado de Carolina",
      exact: true,
    }),
  ).toBeVisible();
});
