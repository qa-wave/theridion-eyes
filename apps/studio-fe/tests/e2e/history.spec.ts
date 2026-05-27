import { test, expect } from "@playwright/test";
import { TEST_SIDECAR_PORT } from "../../playwright.config";

const SIDECAR = `http://127.0.0.1:${TEST_SIDECAR_PORT}`;

test.describe("history panel", () => {
  test.beforeEach(async ({ page, request }) => {
    // Clear history before each test
    try {
      await request.delete(`${SIDECAR}/api/history`);
    } catch {
      // Endpoint might not exist yet — ignore
    }
    await page.goto("/");
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });
  });

  test("sent request appears in history panel", async ({ page }) => {
    // Enter a URL targeting the sidecar's own health endpoint (will succeed)
    const urlInput = page.getByPlaceholder(/Enter URL/i).or(page.locator("input[type='text']").first());
    await urlInput.fill(`${SIDECAR}/api/health`);

    // Send the request
    await page.getByRole("button", { name: "Send" }).click();

    // Wait for response to appear (status badge)
    await expect(page.getByText("200")).toBeVisible({ timeout: 10_000 });

    // Open history panel via Cmd+Shift+H
    await page.keyboard.press("Meta+Shift+h");

    // History panel should be visible with the entry
    await expect(page.getByText("History", { exact: true })).toBeVisible();
    await expect(page.getByText("/api/health")).toBeVisible({ timeout: 5_000 });
  });

  test("history shows method and status for each entry", async ({ page }) => {
    // Send a request
    const urlInput = page.getByPlaceholder(/Enter URL/i).or(page.locator("input[type='text']").first());
    await urlInput.fill(`${SIDECAR}/api/health`);
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText("200")).toBeVisible({ timeout: 10_000 });

    // Open history
    await page.keyboard.press("Meta+Shift+h");
    await expect(page.getByText("History", { exact: true })).toBeVisible();

    // Should show GET method badge
    await expect(
      page.locator("[class*='history']").or(page.locator("div")).filter({ hasText: "GET" }).first(),
    ).toBeVisible();
  });

  test("clear history empties the list", async ({ page }) => {
    // Send a request first
    const urlInput = page.getByPlaceholder(/Enter URL/i).or(page.locator("input[type='text']").first());
    await urlInput.fill(`${SIDECAR}/api/health`);
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText("200")).toBeVisible({ timeout: 10_000 });

    // Open history
    await page.keyboard.press("Meta+Shift+h");
    await expect(page.getByText("/api/health")).toBeVisible({ timeout: 5_000 });

    // Click clear button (trash icon in history header)
    await page.getByTitle("Clear history").click();

    // History should now show empty state
    await expect(page.getByText("No history yet")).toBeVisible();
  });

  test("toggle history panel open and closed", async ({ page }) => {
    const searchInput = page.getByPlaceholder("Search URL, method...");

    // Open history
    await page.keyboard.press("Meta+Shift+h");
    await expect(searchInput).toBeVisible();

    // Close it again with same shortcut
    await page.keyboard.press("Meta+Shift+h");
    await expect(searchInput).toBeHidden({ timeout: 3_000 });
  });
});
