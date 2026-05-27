import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright is on-brand for Theridion: we ourselves want to ship a
 * Playwright-style runner UI, so dogfooding the same tool to test the
 * desktop frontend is the right call.
 *
 * Test isolation:
 *   - Sidecar runs on a dedicated port (8766) so it never collides with
 *     the dev sidecar a developer is running on 8765.
 *   - Sidecar's storage root is forced to /tmp/theridion-e2e via
 *     THERIDION_HOME — globalSetup wipes it before each run so tests
 *     always start with no collections / environments.
 *   - Vite runs on 1421 with VITE_SIDECAR_URL pointing at the test
 *     sidecar, so the frontend bundles know which loopback to hit.
 */

const TEST_SIDECAR_PORT = 8766;
const TEST_VITE_PORT = 1421;
const TEST_HOME = "/tmp/theridion-e2e";
// Fixed token used for all E2E test runs so both sidecar and Vite frontend
// agree on the value without any dynamic discovery.
const TEST_SIDECAR_TOKEN = "playwright-e2e-test-token";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  // The frontend writes to a single sidecar storage root; running tests in
  // parallel against the same root races. Serial keeps the wiring simple
  // until we're ready to per-test sandbox the home.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  globalSetup: "./tests/e2e/global-setup.ts",
  use: {
    baseURL: `http://localhost:${TEST_VITE_PORT}`,
    trace: "on-first-retry",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: `cd ../sidecar && THERIDION_PORT=${TEST_SIDECAR_PORT} THERIDION_HOME=${TEST_HOME} THERIDION_TOKEN=${TEST_SIDECAR_TOKEN} uv run python -m theridion_sidecar.main`,
      url: `http://127.0.0.1:${TEST_SIDECAR_PORT}/api/health`,
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: `pnpm dev --port ${TEST_VITE_PORT}`,
      url: `http://localhost:${TEST_VITE_PORT}`,
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
      env: {
        VITE_SIDECAR_URL: `http://127.0.0.1:${TEST_SIDECAR_PORT}`,
        VITE_SIDECAR_TOKEN: TEST_SIDECAR_TOKEN,
      },
    },
  ],
});

export { TEST_SIDECAR_PORT, TEST_VITE_PORT, TEST_HOME, TEST_SIDECAR_TOKEN };
