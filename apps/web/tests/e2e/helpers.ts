import { expect, type Page } from "@playwright/test";

/** Fase 22: los resultados automáticos viven en la pestaña «Análisis»; «Dataset» se abre
 * primero. La pestaña aparece cuando la carga termina. */
export async function openAnalysis(page: Page) {
  const tab = page.getByRole("tab", { name: "Análisis", exact: true });
  await expect(tab).toBeVisible({ timeout: 30000 });
  await tab.click();
  await expect(tab).toHaveAttribute("aria-selected", "true");
}
