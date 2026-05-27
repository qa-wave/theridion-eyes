import { test, expect } from "@playwright/test";

test.describe("keyboard shortcuts", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });
  });

  test("Cmd+T opens a new tab", async ({ page }) => {
    // Count initial tabs (there's always at least one)
    const initialTabs = await page.locator("[data-tab-id]").or(page.locator("button").filter({ hasText: /Untitled/ })).count();

    await page.keyboard.press("Meta+t");

    // Should have one more tab now
    const newTabs = await page.locator("[data-tab-id]").or(page.locator("button").filter({ hasText: /Untitled/ })).count();
    expect(newTabs).toBeGreaterThan(initialTabs);
  });

  test("Cmd+W closes the active tab", async ({ page }) => {
    // Open a second tab first
    await page.keyboard.press("Meta+t");
    const tabsAfterOpen = await page.locator("[data-tab-id]").or(page.locator("button").filter({ hasText: /Untitled/ })).count();

    await page.keyboard.press("Meta+w");

    const tabsAfterClose = await page.locator("[data-tab-id]").or(page.locator("button").filter({ hasText: /Untitled/ })).count();
    expect(tabsAfterClose).toBeLessThan(tabsAfterOpen);
  });

  test("Cmd+K opens command palette", async ({ page }) => {
    await page.keyboard.press("Meta+k");
    await expect(page.getByPlaceholder(/Type a command/i)).toBeVisible();
  });

  test("Cmd+K toggles command palette closed", async ({ page }) => {
    await page.keyboard.press("Meta+k");
    await expect(page.getByPlaceholder(/Type a command/i)).toBeVisible();

    await page.keyboard.press("Meta+k");
    await expect(page.getByPlaceholder(/Type a command/i)).toBeHidden();
  });

  test("Cmd+, opens settings", async ({ page }) => {
    await page.keyboard.press("Meta+,");
    await expect(page.getByRole("button", { name: "General", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "About", exact: true })).toBeVisible();
  });

  test("Cmd+Enter sends request", async ({ page }) => {
    // The send button should work even without URL (will likely error)
    // We just verify the action triggers by watching for response panel change
    const sendBtn = page.getByRole("button", { name: "Send" });
    await expect(sendBtn).toBeVisible();

    // Enter a valid URL first
    const urlInput = page.getByPlaceholder(/Enter URL/i).or(page.locator("input[type='text']").first());
    await urlInput.fill("http://127.0.0.1:8766/api/health");

    await page.keyboard.press("Meta+Enter");

    // Should get a response (200 from health endpoint)
    await expect(page.getByText("200")).toBeVisible({ timeout: 10_000 });
  });

  test("Alt+1 switches to Params tab", async ({ page }) => {
    // First switch away from Params
    await page.keyboard.press("Alt+2");
    await expect(page.getByText("Headers", { exact: false })).toBeVisible();

    // Switch back to Params
    await page.keyboard.press("Alt+1");
    await expect(page.getByText("Query parameters", { exact: true })).toBeVisible();
  });

  test("Alt+2 switches to Headers tab", async ({ page }) => {
    await page.keyboard.press("Alt+2");
    // Headers view has table/raw mode toggle
    await expect(
      page.getByRole("button", { name: /Table/i }).or(page.getByText("Table")),
    ).toBeVisible();
  });

  test("Alt+3 switches to Body tab", async ({ page }) => {
    await page.keyboard.press("Alt+3");
    // Body tab shows content-type preset buttons or an editor
    await expect(
      page.getByText("Body", { exact: true }).or(page.getByText("Content-Type")),
    ).toBeVisible();
  });

  test("Alt+4 switches to Auth tab", async ({ page }) => {
    await page.keyboard.press("Alt+4");
    await expect(page.getByText("Type", { exact: true })).toBeVisible();
    await expect(page.getByTestId("auth-type-select")).toBeVisible();
  });

  test("Escape closes command palette", async ({ page }) => {
    await page.keyboard.press("Meta+k");
    await expect(page.getByPlaceholder(/Type a command/i)).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByPlaceholder(/Type a command/i)).toBeHidden();
  });

  test("Escape closes settings modal", async ({ page }) => {
    await page.keyboard.press("Meta+,");
    await expect(page.getByRole("button", { name: "General", exact: true })).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "General", exact: true })).toBeHidden();
  });
});
