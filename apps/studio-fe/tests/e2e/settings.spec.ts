import { test, expect } from "@playwright/test";

test.describe("settings modal", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });
  });

  test("opens settings via Cmd+,", async ({ page }) => {
    await page.keyboard.press("Meta+,");
    await expect(page.getByText("Settings", { exact: false }).first()).toBeVisible();
  });

  test("all tabs are visible in settings sidebar", async ({ page }) => {
    await page.keyboard.press("Meta+,");

    // Verify all 6 tabs exist
    await expect(page.getByRole("button", { name: "General", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "AI", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Editor", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Proxy", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Shortcuts", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "About", exact: true })).toBeVisible();
  });

  test("general tab shows theme options", async ({ page }) => {
    await page.keyboard.press("Meta+,");

    // General tab should be active by default — theme section visible
    await expect(page.getByText("Theme", { exact: true })).toBeVisible();
  });

  test("switching to Editor tab shows font size setting", async ({ page }) => {
    await page.keyboard.press("Meta+,");
    await page.getByRole("button", { name: "Editor", exact: true }).click();

    await expect(page.getByText("Font Size")).toBeVisible();
    // Font size input should exist with default value
    const fontInput = page.locator("input[type='number']").first();
    await expect(fontInput).toBeVisible();
    await expect(fontInput).toHaveValue("12");
  });

  test("switching to AI tab shows provider selection", async ({ page }) => {
    await page.keyboard.press("Meta+,");
    await page.getByRole("button", { name: "AI", exact: true }).click();

    await expect(page.getByText("Provider")).toBeVisible();
    // Default provider is Ollama
    await expect(page.getByTestId("ai-provider-select")).toHaveValue("ollama");
  });

  test("switching to Proxy tab shows proxy configuration", async ({ page }) => {
    await page.keyboard.press("Meta+,");
    await page.getByRole("button", { name: "Proxy", exact: true }).click();

    await expect(page.getByText("HTTP Proxy")).toBeVisible();
    await expect(page.getByText("SSL / TLS")).toBeVisible();
    await expect(page.getByPlaceholder("http://proxy.corp:8080")).toBeVisible();
  });

  test("switching to Shortcuts tab lists key bindings", async ({ page }) => {
    await page.keyboard.press("Meta+,");
    await page.getByRole("button", { name: "Shortcuts", exact: true }).click();

    await expect(page.getByText("Send request")).toBeVisible();
    await expect(page.getByText("New tab")).toBeVisible();
    await expect(page.getByText("Command palette")).toBeVisible();
  });

  test("switching to About tab shows app info", async ({ page }) => {
    await page.keyboard.press("Meta+,");
    await page.getByRole("button", { name: "About", exact: true }).click();

    await expect(page.getByText("Theridion").first()).toBeVisible();
    await expect(page.getByText("v0.0.1")).toBeVisible();
    await expect(page.getByText("Modern API testing platform")).toBeVisible();
  });

  test("close settings with Cancel button", async ({ page }) => {
    await page.keyboard.press("Meta+,");
    await expect(page.getByText("Theme", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Cancel" }).click();
    // Modal should disappear
    await expect(page.getByText("Theme", { exact: true })).toBeHidden();
  });

  test("editor font size can be changed", async ({ page }) => {
    await page.keyboard.press("Meta+,");
    await page.getByRole("button", { name: "Editor", exact: true }).click();

    const fontInput = page.locator("input[type='number']").first();
    await fontInput.fill("14");
    await expect(fontInput).toHaveValue("14");
  });
});
