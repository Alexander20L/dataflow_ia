import { expect, test } from "@playwright/test";

// Fase 28: criterio analítico. En un padrón de empleados la fecha de ingreso describe a cada
// persona (no es una línea de tiempo) y la columna «activo» se analiza como tasa: 9 bajas de 100.
test("Criterio: fecha que describe al registro, sin evolución mensual", async ({
  page,
}) => {
  test.setTimeout(150_000);
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista Criterio",
      email: `criterio-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-Criterio-123",
    },
  });
  expect(registration.status()).toBe(201);
  const lines = [
    "empleado_id,area,cargo,fecha_ingreso,salario,evaluacion,dias_ausencia,activo",
  ];
  const start = Date.UTC(2015, 0, 15);
  for (let i = 0; i < 100; i++) {
    const area = "ABCDE"[Math.floor(i / 20)];
    const inactive = i % 20 < (area === "A" ? 5 : 1);
    const day = new Date(start + 37 * i * 86_400_000)
      .toISOString()
      .slice(0, 10);
    lines.push(
      `E${String(i).padStart(3, "0")},${area},` +
        `${["Analista", "Asistente", "Jefe", "Supervisor"][i % 4]},${day},` +
        `${3000 + 400 * (i % 5) + 7 * i},${(1 + (i % 9) / 2).toFixed(1)},${i % 6},` +
        `${inactive ? "No" : "Sí"}`,
    );
  }
  await page.goto("/new");
  await page.locator('input[type="file"]').setInputFiles({
    name: "empleados.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(lines.join("\n") + "\n"),
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();

  // Comprensión: la fecha de ingreso describe al registro y se cuenta por año.
  await page
    .getByRole("tab", { name: "Comprensión", exact: true })
    .click({ timeout: 30000 });
  const tab = page.getByRole("region", { name: "Comprensión" });
  const dated = tab.getByLabel("Fechas que describen al registro");
  await expect(dated).toContainText("fecha_ingreso", { timeout: 60000 });
  await expect(dated).toContainText("no es una línea de tiempo");
  await expect(tab.getByLabel("Periodo")).toHaveCount(0);

  // Dashboard: sin evolución mensual (la fecha describe a cada empleado). Desde la Fase 29 la
  // tasa por área (25 % frente a 5 % con 20 personas por área) no es significativa y no aparece
  // como hallazgo.
  await page.getByRole("tab", { name: "Dashboard", exact: true }).click();
  const board = page.getByRole("region", { name: "Dashboard", exact: true });
  await expect(board.getByText("Diseñado por la IA")).toBeVisible({
    timeout: 90000,
  });
  await expect(board.getByText(/Evolución mensual/)).toHaveCount(0);
  await expect(
    board.getByRole("article", { name: /en activo por area$/ }),
  ).toHaveCount(0);
});
