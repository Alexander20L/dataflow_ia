import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const apiDir = path.resolve(__dirname, "../api");
const python =
  process.env.DATAFLOW_PYTHON ??
  path.join(
    apiDir,
    process.platform === "win32"
      ? ".venv/Scripts/python.exe"
      : ".venv/bin/python",
  );
const e2eDatabase =
  process.env.DATAFLOW_E2E_DATABASE_URL ??
  "postgresql+psycopg://dataflow:dataflow_local@127.0.0.1:55432/dataflow_e2e";
if (!new URL(e2eDatabase).pathname.endsWith("_e2e"))
  throw new Error("Las pruebas E2E requieren una base terminada en _e2e.");

export default defineConfig({
  testDir: "./tests/e2e",
  // En serie: todas las pruebas comparten una API y un único worker de cola. En paralelo
  // sólo compiten por él (también en CI, donde Playwright usaría la mitad de los núcleos)
  // y agotan sus esperas de procesamiento.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `"${python}" -m dataflow.bootstrap.run --port 8001 --with-worker`,
      cwd: apiDir,
      env: {
        DATAFLOW_DATABASE_URL: e2eDatabase,
        DATAFLOW_STORAGE_PATH: ".data/e2e-objects",
      },
      url: "http://127.0.0.1:8001/health/ready",
      reuseExistingServer: false,
      timeout: 90000,
    },
    {
      command: "npm run start -- --port 3100",
      env: { API_INTERNAL_URL: "http://127.0.0.1:8001" },
      url: "http://127.0.0.1:3100",
      reuseExistingServer: false,
      timeout: 90000,
    },
  ],
});
