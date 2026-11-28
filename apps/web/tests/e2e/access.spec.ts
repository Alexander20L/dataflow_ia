import { expect, test } from "@playwright/test";

// Entrar desde /login o /register lleva al inicio, no a «Página no encontrada».
test("registro desde /register e inicio de sesión desde /login terminan en el inicio", async ({
  page,
}) => {
  const email = `acceso-${crypto.randomUUID()}@example.com`;
  const password = "Una-contraseña-de-prueba-123";

  await page.goto("/register");
  await expect(
    page.getByRole("heading", { name: "Crea tu cuenta" }),
  ).toBeVisible();
  await page.getByLabel("Nombre", { exact: true }).fill("Lucía");
  await page.getByLabel("Correo electrónico").fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Hola, Lucía" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/$/);

  await page.context().clearCookies();
  await page.goto("/login");
  await expect(
    page.getByRole("heading", { name: "Bienvenido de nuevo" }),
  ).toBeVisible();
  await page.getByLabel("Correo electrónico").fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(
    page.getByRole("heading", { name: "Hola, Lucía" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByText("Página no encontrada")).toHaveCount(0);

  // Con la sesión abierta, abrir /login también vuelve al inicio.
  await page.goto("/login");
  await expect(page).toHaveURL(/\/$/);
  await expect(
    page.getByRole("heading", { name: "Hola, Lucía" }),
  ).toBeVisible();
});
