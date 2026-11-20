import { expect, test } from "@playwright/test";

const FILES = [
  {
    name: "asistencia.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "id,id_estudiante,fecha,asistio\n" +
        "1,10,2026-03-02,si\n" +
        "2,11,2026-03-02,no\n" +
        "3,10,2026-03-09,si\n" +
        "4,12,2026-03-09,si\n" +
        "5,11,2026-03-09,si\n",
    ),
  },
  {
    name: "notas.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "id_estudiante,curso,nota\n10,Mate,15\n10,Física,14\n11,Mate,10\n12,Mate,17.5\n",
    ),
  },
  {
    name: "estudiantes.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "id,nombre,id_carrera\n10,Ana,1\n11,Luis,2\n12,Eva,1\n",
    ),
  },
  {
    name: "carreras.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("id,carrera\n1,Sistemas\n2,Civil\n"),
  },
];

// Fase 31: «Cargar varios archivos relacionados». Dos tablas de hechos (asistencia y notas) que
// apuntan a estudiantes, que apunta a carreras: el esquema se ve antes de analizar y la versión
// que se abre es la vista general por estudiante con métricas de asistencia y notas.
test("Archivos relacionados: foto del esquema y vista general de todas las tablas", async ({
  page,
}) => {
  // Siete versiones (cuatro tablas, dos vistas de hechos y la general) pasan por todo el recorrido.
  test.setTimeout(150000);
  const registration = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:3100" },
    data: {
      name: "Analista Relaciones",
      email: `related-${crypto.randomUUID()}@example.com`,
      password: "Prueba-segura-Relaciones-123",
    },
  });
  expect(registration.status()).toBe(201);
  await page.goto("/new");
  const modes = page.getByRole("radiogroup", { name: "Cómo traer los datos" });
  await expect(
    modes.getByRole("radio", { name: /Cargar archivo/ }),
  ).toHaveAttribute("aria-checked", "true");
  await modes.getByRole("radio", { name: /Conectar base de datos/ }).click();
  await expect(page.getByLabel("Servidor")).toBeVisible();
  await expect(page.getByLabel("Esquema")).toHaveValue("");
  await page.getByText("PostgreSQL", { exact: true }).click();
  await expect(page.getByLabel("Esquema")).toHaveValue("public");
  await expect(page.getByLabel("Puerto")).toHaveValue("5432");

  await modes
    .getByRole("radio", { name: /Cargar varios archivos relacionados/ })
    .click();
  await page.getByLabel("Archivos relacionados").setInputFiles(FILES);
  const selected = page.getByRole("list", { name: "Archivos seleccionados" });
  await expect(selected.getByRole("listitem")).toHaveCount(4);
  await expect(page.getByLabel("Nombre del proyecto")).toHaveValue(
    "asistencia",
  );

  // Foto del esquema antes de analizar: no guarda versiones.
  await page.getByRole("button", { name: "Ver esquema" }).click();
  const schema = page.getByRole("region", { name: "Esquema" });
  await expect(
    schema.getByRole("img", { name: /Diagrama del esquema: 4 tablas/ }),
  ).toBeVisible({ timeout: 30000 });
  await expect(schema).toContainText(
    "se abre primero «estudiantes (vista general)»",
  );
  await expect(
    schema.getByRole("row", { name: /notas\.csv Tabla de hechos/ }),
  ).toBeVisible();
  await expect(
    schema.getByRole("list", { name: "Vistas que se analizan" }),
  ).toContainText("asistencia (tablas unidas)");

  await page.getByRole("button", { name: "Continuar al análisis" }).click();
  const related = page.getByRole("region", { name: "Tablas relacionadas" });
  await expect(
    related.getByRole("heading", {
      name: "Vista general de todas las tablas relacionadas",
    }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    related.getByRole("row", { name: /estudiantes\.csv Entidad principal 3/ }),
  ).toBeVisible();
  await expect(
    related.getByRole("list", { name: "Relaciones encontradas" }),
  ).toContainText("notas.csv.id_estudiante → estudiantes.csv.id");

  // La vista general se analiza como una carga: un registro por estudiante con sus métricas.
  const tab = page.getByRole("tab", { name: "Dataset", exact: true });
  await expect(tab).toHaveAttribute("aria-selected", "true", {
    timeout: 60000,
  });
  await page.getByRole("tab", { name: "Registros" }).click({ timeout: 90000 });
  const table = page.getByRole("table").last();
  await expect(
    table.getByRole("columnheader", { name: /promedio de nota/ }).first(),
  ).toBeVisible({ timeout: 30000 });
  await expect(table.getByRole("cell", { name: "14.5" }).first()).toBeVisible();
});
