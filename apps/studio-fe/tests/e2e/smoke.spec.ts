import { test, expect } from "@playwright/test";

test.describe("smoke", () => {
  test("app boots and reports a healthy sidecar", async ({ page }) => {
    await page.goto("/");

    // Status bar shows "sidecar v0.0.1" once the health check completes.
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });

    // Sidebar header is visible. (Whether collections render depends on
    // what previous tests in this run wrote — we don't assert empty state
    // here, that's covered in collections.spec.ts.)
    await expect(page.getByText(/Collections/i).first()).toBeVisible();

    // The default tab is open with method=GET and a Send button.
    await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
  });

  test("env dropdown defaults to 'No env'", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTitle("No environment", { exact: true })).toBeVisible();
  });
});
