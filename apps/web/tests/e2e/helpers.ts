import { expect, type Page } from "@playwright/test";

/** Abre una pestaña de la versión. Fase 22: «Dataset» se abre primero; las pestañas aparecen
 * cuando la carga termina. Fase 28: ya no hay pestaña «Análisis». */
export async function openTab(page: Page, name: string) {
  const tab = page.getByRole("tab", { name, exact: true });
  await expect(tab).toBeVisible({ timeout: 30000 });
  await tab.click();
  await expect(tab).toHaveAttribute("aria-selected", "true");
}

/** Fase 28: los hallazgos del análisis automático (Fase 15) están en Investigación. */
export async function openFindings(page: Page) {
  await openTab(page, "Investigación");
  const investigation = page.getByRole("region", {
    name: "Investigación",
    exact: true,
  });
  await investigation
    .getByRole("tab", { name: "Hallazgos del análisis" })
    .click({ timeout: 60000 });
  return page.getByRole("region", {
    name: "Hallazgos del análisis automático",
  });
}

/** Fase 28: los registros de la versión (antes, «Detalle de los datos» en Análisis). */
export async function openRecords(page: Page) {
  await openTab(page, "Dataset");
  await page.getByRole("tab", { name: "Registros" }).click({ timeout: 30000 });
}

/** Fase 28: la lectura del archivo (antes, «Lectura del archivo» en Análisis). */
export async function openFile(page: Page) {
  await openTab(page, "Dataset");
  await page.getByRole("tab", { name: "Archivo" }).click({ timeout: 30000 });
}
