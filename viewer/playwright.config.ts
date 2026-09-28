import { resolve } from "node:path";
import { defineConfig } from "@playwright/test";

/**
 * One end-to-end test of the MVP flow, on a synthetic export only (no provider
 * data). It runs its own dev server on port 5174, so it never touches the
 * exports in out/exports, and it uses the locally installed Chrome.
 */
const PORT = 5174;
const E2E_EXPORTS = resolve(import.meta.dirname, "e2e/.exports");

export default defineConfig({
  testDir: "e2e",
  testMatch: "*.e2e.ts",
  outputDir: "test-results",
  globalSetup: "./e2e/globalSetup.ts",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: `http://localhost:${PORT}`,
    channel: "chrome",
    trace: "retain-on-failure",
  },
  webServer: {
    command: `npm run dev -- --port ${PORT}`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: false,
    env: { REGISTA_EXPORTS_DIR: E2E_EXPORTS },
    timeout: 60_000,
  },
});
