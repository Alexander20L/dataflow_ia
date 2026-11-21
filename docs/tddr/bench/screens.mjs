// Capturas de las pantallas clave para el TDDR (sección 3.3). Requiere la web en WEB_URL
// apuntando a una API con worker. Uso (desde apps/web):
//   node ../../docs/tddr/bench/screens.mjs http://localhost:3005
import { chromium } from "@playwright/test";
import { readFileSync, readdirSync, mkdirSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = process.argv[2] ?? "http://localhost:3005";
const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../../..");
const out = resolve(here, "../img");
mkdirSync(out, { recursive: true });
const folder = join(root, "examples", "relacionadas");
const files = readdirSync(folder)
  .filter((f) => f.endsWith(".csv"))
  .map((name) => ({
    name,
    mimeType: "text/csv",
    buffer: readFileSync(join(folder, name)),
  }));

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  locale: "es-PE",
});
const shot = (name, opts = {}) =>
  page.screenshot({ path: join(out, `${name}.png`), ...opts });

await page.goto(`${WEB}/`);
await page.waitForLoadState("networkidle");
await shot("01-acceso");

const reg = await page.request.post(`${WEB}/api/v1/auth/register`, {
  headers: { Origin: WEB },
  data: {
    name: "Analista TDDR",
    email: `tddr-${crypto.randomUUID()}@example.com`,
    password: "Capturas-TDDR-segura-2026",
  },
});
if (reg.status() !== 201) throw new Error(`registro ${reg.status()}`);

await page.goto(`${WEB}/new`);
const modes = page.getByRole("radiogroup", { name: "Cómo traer los datos" });
await modes
  .getByRole("radio", { name: /Cargar varios archivos relacionados/ })
  .click();
await page.getByLabel("Archivos relacionados").setInputFiles(files);
await shot("02-carga-tres-opciones");
await page.getByRole("button", { name: "Ver esquema" }).click();
const schema = page.getByRole("region", { name: "Esquema" });
await schema
  .getByRole("img", { name: /Diagrama del esquema/ })
  .waitFor({ timeout: 60000 });
await schema.screenshot({ path: join(out, "03-foto-del-esquema.png") });

await page.getByRole("button", { name: "Continuar al análisis" }).click();
await page
  .getByRole("tab", { name: "Dataset", exact: true })
  .waitFor({ timeout: 90000 });
// Espera a que todas las versiones del proyecto completen sus etapas.
const api = (path) =>
  page.request.get(`${WEB}/api/v1${path}`).then((r) => r.json());
for (let i = 0; i < 600; i++) {
  const projects = await api("/projects");
  const project = (projects.items ?? projects)[0];
  const versions = await api(`/projects/${project.id}/versions`);
  const items = versions.items ?? versions;
  const states = await Promise.all(
    items.map((v) => api(`/versions/${v.id}/progress`)),
  );
  if (items.length && states.every((s) => s.complete)) break;
  await page.waitForTimeout(2000);
}
await page.reload();
await page.waitForLoadState("networkidle");
const tabs = [
  ["Dataset", "04-dataset"],
  ["Comprensión", "05-comprension"],
  ["Investigación", "06-investigacion"],
  ["Dashboard", "07-dashboard"],
  ["Informe", "08-informe"],
];
for (const [name, file] of tabs) {
  const tab = page.getByRole("tab", { name, exact: true }).first();
  await tab.click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(2000);
  await tab.evaluate((el) => el.scrollIntoView({ block: "start" }));
  await page.waitForTimeout(500);
  await shot(file, { fullPage: false });
}
await browser.close();
console.log("capturas en", out);
