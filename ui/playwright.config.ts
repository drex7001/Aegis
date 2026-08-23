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
  /*
   * Capped, and the cap is measured rather than guessed.
   *
   * Playwright defaults to half the available cores. On a 16-core machine that
   * is 8 workers, and several of these journeys drive MapLibre through a
   * software renderer — so they compete for the same CPU and time out. On a
   * GitHub runner (2-4 cores) the default is 1-2 workers, which is why CI has
   * never seen it and three separate local runs did.
   *
   * Measured on this suite at 151 tests: 8 workers failed 2-4 map-heavy
   * journeys per run and every one of them passed in isolation; 4 workers
   * passed all 151. The cap is below what CI already uses, so it costs CI
   * nothing and stops the next person on a large machine rediscovering this.
   *
   * `retries` stays 0. A retry would have made the same runs green while
   * hiding the reason, which is the opposite of what was needed to find it.
   */
  workers: 4,
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
