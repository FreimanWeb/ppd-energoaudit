import { defineConfig } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const data = mkdtempSync(join(tmpdir(), "ppd-e2e-"));
const python = join(root, ".venv/bin/python");
const env = {
  PPD_DATABASE_PATH: join(data, "audit.sqlite"),
  PPD_CRM_DIR: join(data, "crm"),
  PPD_SCADA_TAGS_PATH: join(data, "tags.yaml"),
  PPD_DOWNTIME_DIR: join(data, "downtime"),
  PPD_APP_PASSWORD: "",
  PPD_SKIP_EXAMPLE_TELEMETRY: "1",
  PPD_SKIP_SCADA_TELEMETRY: "1",
};
export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:5181",
    trace: "retain-on-failure",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    },
  },
  webServer: [
    {
      command: `${python} scripts/seed_e2e.py ${data} && ${python} -m uvicorn ppd_audit.api.main:app --host 127.0.0.1 --port 8181`,
      cwd: root,
      env,
      url: "http://127.0.0.1:8181/health",
      reuseExistingServer: false,
      timeout: 60000,
    },
    {
      command: `${python} -m uvicorn ppd_audit.api.main:app --host 127.0.0.1 --port 8191`,
      cwd: root,
      env: {
        ...env,
        PPD_APP_PASSWORD: "e2e-known-password",
        PPD_SESSION_SECRET: "e2e-session-secret-for-isolated-local-tests-only",
      },
      url: "http://127.0.0.1:8191/health",
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5191 --strictPort",
      env: { VITE_API_PROXY_TARGET: "http://127.0.0.1:8191" },
      url: "http://127.0.0.1:5191",
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5181 --strictPort",
      env: { VITE_API_PROXY_TARGET: "http://127.0.0.1:8181" },
      url: "http://127.0.0.1:5181",
      reuseExistingServer: false,
    },
  ],
});
