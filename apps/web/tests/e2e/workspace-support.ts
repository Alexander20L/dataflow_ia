import { expect, type Page } from "@playwright/test";

/** Las pruebas de edición avanzada entran explícitamente; el recorrido normal no lo necesita. */
export async function openAdvanced(page: Page) {
  const toggle = page.getByRole("button", {
    name: "Herramientas avanzadas (opcionales)",
    exact: true,
  });
  await expect(toggle).toBeVisible();
  await toggle.click();
  await expect(
    page.getByRole("button", { name: "Ocultar herramientas avanzadas" }),
  ).toHaveAttribute("aria-expanded", "true");
}
