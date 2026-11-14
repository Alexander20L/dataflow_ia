import { expect, test } from "@playwright/test";

// Fase 29: analista con objetivo. En una plantilla de 300 personas, las bajas («activo» = No) se
// concentran en el primer año y en Marketing: el análisis lo dice con su prueba estadística, lo
// comprueba con la antigüedad y el usuario puede cambiar el objetivo.
test("Analista: objetivo, factores con significancia y cambio de objetivo", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista Objetivo",
      email: `objetivo-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-Objetivo-123",
    },
  });
  expect(registration.status()).toBe(201);
  const areas = ["Comercial", "Finanzas", "Logística", "Marketing", "Ventas"];
  const reference = Date.UTC(2025, 11, 31);
  const lines = ["empleado_id,area,fecha_ingreso,salario,activo"];
  for (let i = 0; i < 300; i++) {
    const area = areas[Math.floor(i / 60)];
    const k = i % 60;
    const newbie = k < (area === "Ventas" ? 30 : 10);
    const days = newbie
      ? 30 + ((k * 11) % 300) + 3 * Math.floor(i / 60)
      : 400 + 23 * i;
    const left = newbie
      ? k % 3 === 0
      : area === "Marketing"
        ? k % 10 < 3
        : k % 20 === 0;
    const day = new Date(reference - days * 86_400_000)
      .toISOString()
      .slice(0, 10);
    lines.push(
      `E${String(i).padStart(3, "0")},${area},${day},${3000 + 37 * k},${left ? "No" : "Sí"}`,
    );
  }
  await page.goto("/new");
  await page.locator('input[type="file"]').setInputFiles({
    name: "plantilla.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(lines.join("\n") + "\n"),
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();

  // Comprensión: el objetivo propuesto (la IA de pruebas elige la columna de dos valores).
  await page
    .getByRole("tab", { name: "Comprensión", exact: true })
    .click({ timeout: 30000 });
  const tab = page.getByRole("region", { name: "Comprensión" });
  const target = tab.getByLabel("Objetivo del análisis");
  await expect(target).toContainText("«activo»", { timeout: 60000 });
  await expect(target).toContainText("antigüedad de fecha_ingreso");

  // Investigación: los factores llevan su prueba y su comprobación con otra variable.
  await page.getByRole("tab", { name: "Investigación", exact: true }).click();
  const investigation = page.getByRole("region", {
    name: "Investigación",
    exact: true,
  });
  await investigation
    .getByRole("tab", { name: /^Evidencias/ })
    .click({ timeout: 90000 });
  await expect(
    investigation.getByText("Significancia estadística").first(),
  ).toBeVisible({ timeout: 90000 });
  await expect(
    investigation.getByText("Comprobación con otra variable").first(),
  ).toBeVisible();

  // El usuario cambia el objetivo: se rehace el análisis con el salario.
  await page.getByRole("tab", { name: "Comprensión", exact: true }).click();
  await tab.getByLabel("Objetivo", { exact: true }).selectOption("salario");
  await tab.getByRole("button", { name: "Usar este objetivo" }).click();
  await expect(tab.getByLabel("Objetivo del análisis")).toContainText(
    "El promedio de «salario»",
    { timeout: 90000 },
  );
  await expect(tab.getByLabel("Objetivo del análisis")).toContainText(
    "Elegido por ti",
  );
});
