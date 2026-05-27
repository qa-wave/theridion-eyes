import { test, expect } from "@playwright/test";

// Resilience-focused E2E: the desktop shell boots and the bundled sidecar
// reports healthy, independent of any collection/auth state.
test.describe("health & resilience", () => {
  test("app boots and sidecar reports healthy", async ({ page }) => {
    const res = await page.goto("/");
    expect(res?.status()).toBeLessThan(400);
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({
      timeout: 10_000,
    });
  });

  test("core request UI is available", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
  });

  test("boots without uncaught page errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto("/");
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({
      timeout: 10_000,
    });
    expect(errors, errors.join("\n")).toHaveLength(0);
  });
});
