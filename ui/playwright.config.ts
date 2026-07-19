import { defineConfig, devices } from "@playwright/test";

/**
 * The T22 smoke journey runs against the **built** bundle via `vite preview`,
 * not the dev server: a workspace that only works unminified is not a shipped
 * workspace, and the OIDC redirect round trip is exactly the kind of thing HMR
 * papers over.
 *
 * The full ingest → suggest → review → adjudicate loop against a live stack is
 * T25/T27's blocking demo. This job stays hermetic — no Python, no database, no
 * Keycloak — so a UI change gets its answer in seconds.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: true,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run preview",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
