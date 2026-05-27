import { rmSync } from "node:fs";
import { TEST_HOME } from "../../playwright.config";

/**
 * Nukes the test storage directory so every Playwright run starts with
 * zero collections and zero environments. The sidecar webServer
 * recreates the subdirectories lazily on first write.
 */
export default async function globalSetup() {
  try {
    rmSync(TEST_HOME, { recursive: true, force: true });
  } catch {
    // First run — nothing to delete.
  }
}
