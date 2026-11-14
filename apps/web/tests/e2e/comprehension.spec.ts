import { expect, test } from "@playwright/test";

// Fase 24: pestaña Comprensión. «promedio» es 0,3·parcial + 0,4·final + 0,3·prácticas y
// «aprobado» es «Sí» desde 10,5: se muestran como fórmulas, no como hallazgos; el significado de
// una columna se puede escribir y no cambia ningún cálculo.
test("Comprensión: grano, fórmulas, relaciones por familia y significado propio", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista Comprensión",
      email: `comprension-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-Comprension-123",
    },
  });
  expect(registration.status()).toBe(201);
  const lines = [
    "estudiante_id,carrera,horas,nota_parcial,nota_final,nota_practicas,promedio,aprobado",
  ];
  for (let i = 1; i <= 24; i++) {
    const p = 6 + ((i * 7) % 10) + (i % 3) / 10;
    const f = 5 + ((i * 3) % 12) + (i % 5) / 10;
    const pr = 7 + ((i * 5) % 9) + (i % 4) / 10;
    const avg = Math.round((0.3 * p + 0.4 * f + 0.3 * pr) * 100) / 100;
    lines.push(
      `E${String(i).padStart(3, "0")},${["Derecho", "Medicina", "Arquitectura"][i % 3]},` +
        `${3 + ((i * 7) % 11)},${p.toFixed(1)},${f.toFixed(1)},${pr.toFixed(1)},` +
        `${avg.toFixed(2)},${avg >= 10.5 ? "Sí" : "No"}`,
    );
  }
  await page.goto("/new");
  await page.locator('input[type="file"]').setInputFiles({
    name: "notas.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(lines.join("\n") + "\n"),
  });
  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  await page
    .getByRole("tab", { name: "Comprensión", exact: true })
    .click({ timeout: 30000 });
  const tab = page.getByRole("region", { name: "Comprensión" });

  // Resumen: el grano y las fórmulas comprobadas fila a fila.
  await expect(tab.getByLabel("Grano del dataset")).toContainText(
    "Cada fila es un registro de estudiante, único por «estudiante_id».",
    { timeout: 60000 },
  );
  const formulas = tab.getByLabel("Columnas calculadas");
  await expect(formulas).toContainText(
    "promedio = 0,3·nota_parcial + 0,4·nota_final + 0,3·nota_practicas",
  );
  await expect(formulas).toContainText("aprobado = «Sí» cuando promedio ≥");

  // Relaciones: las fórmulas son estructurales.
  await tab.getByRole("tab", { name: "Relaciones" }).click();
  await tab.getByRole("button", { name: /^Estructurales/ }).click();
  const derived = tab
    .getByRole("listitem", { name: /Relación promedio – nota_final/ })
    .first();
  await expect(derived).toContainText("Columna calculada");
  await expect(derived).toContainText("Pendiente");

  // Columnas: el significado escrito por el usuario.
  await tab.getByRole("tab", { name: "Columnas" }).click();
  await tab
    .getByRole("button", { name: "Editar el significado de horas" })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Significado").fill("Horas de estudio por semana");
  await dialog.getByRole("button", { name: "Guardar significado" }).click();
  const row = tab.getByRole("row", { name: /^horas/ });
  await expect(row).toContainText("Horas de estudio por semana");
  await expect(row).toContainText("Escrito por ti");

  // Fase 24B: tipo técnico y naturaleza de la pestaña Dataset, y una columna desconocida.
  await expect(row).toContainText("Entero");
  await expect(row).toContainText("Cuantitativa discreta");
  await tab
    .getByRole("button", { name: "Editar el significado de carrera" })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Marcar como desconocida" })
    .click();
  await expect(tab.getByRole("row", { name: /^carrera/ })).toContainText(
    "Marcada por ti",
  );

  // El rol se cambia en el Diccionario de la pestaña Dataset.
  await tab
    .getByRole("button", { name: "Cambiar el rol en el Diccionario" })
    .click();
  await expect(
    page.getByRole("tab", { name: "Diccionario", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
});
