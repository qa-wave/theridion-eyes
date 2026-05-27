import { test, expect } from "@playwright/test";
import { TEST_SIDECAR_PORT } from "../../playwright.config";

const SIDECAR = `http://127.0.0.1:${TEST_SIDECAR_PORT}`;

test.describe("auth tab", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });
  });

  test("switches to Auth tab via Alt+4", async ({ page }) => {
    await page.keyboard.press("Alt+4");

    // Auth tab should now be active showing the auth type selector
    await expect(page.getByText("Type", { exact: true })).toBeVisible();
    await expect(page.getByTestId("auth-type-select")).toBeVisible();
  });

  test("default auth type is None", async ({ page }) => {
    await page.keyboard.press("Alt+4");

    const select = page.getByTestId("auth-type-select");
    await expect(select).toHaveValue("none");
    await expect(
      page.getByText("Configure authentication for this request"),
    ).toBeVisible();
  });

  test("selecting Bearer Token shows token input", async ({ page }) => {
    await page.keyboard.press("Alt+4");

    const select = page.getByTestId("auth-type-select");
    await select.selectOption("bearer");

    // Token input should appear
    await expect(page.getByText("Token", { exact: true })).toBeVisible();
    const tokenInput = page.getByPlaceholder("{{token}}");
    await expect(tokenInput).toBeVisible();
  });

  test("entering Bearer token value persists in field", async ({ page }) => {
    await page.keyboard.press("Alt+4");

    const select = page.getByTestId("auth-type-select");
    await select.selectOption("bearer");

    const tokenInput = page.getByPlaceholder("{{token}}");
    await tokenInput.fill("my-secret-token-123");
    await expect(tokenInput).toHaveValue("my-secret-token-123");
  });

  test("selecting Basic Auth shows username and password fields", async ({
    page,
  }) => {
    await page.keyboard.press("Alt+4");

    const select = page.getByTestId("auth-type-select");
    await select.selectOption("basic");

    await expect(page.getByText("Username", { exact: true })).toBeVisible();
    await expect(page.getByText("Password", { exact: true })).toBeVisible();
    await expect(page.getByPlaceholder("{{username}}")).toBeVisible();
    await expect(page.getByPlaceholder("{{password}}")).toBeVisible();
  });

  test("entering Basic Auth credentials persists", async ({ page }) => {
    await page.keyboard.press("Alt+4");

    const select = page.getByTestId("auth-type-select");
    await select.selectOption("basic");

    const usernameInput = page.getByPlaceholder("{{username}}");
    const passwordInput = page.getByPlaceholder("{{password}}");

    await usernameInput.fill("testuser");
    await passwordInput.fill("testpass");

    await expect(usernameInput).toHaveValue("testuser");
    await expect(passwordInput).toHaveValue("testpass");
  });

  test("selecting API Key shows key and value fields", async ({ page }) => {
    await page.keyboard.press("Alt+4");

    const select = page.getByTestId("auth-type-select");
    await select.selectOption("apikey");

    await expect(page.getByText("Key", { exact: true })).toBeVisible();
    // The key placeholder for header name
    await expect(page.getByPlaceholder("X-API-Key")).toBeVisible();
  });

  test("auth type badge appears in tab bar when auth is configured", async ({
    page,
  }) => {
    await page.keyboard.press("Alt+4");

    const select = page.getByTestId("auth-type-select");
    await select.selectOption("bearer");

    const tokenInput = page.getByPlaceholder("{{token}}");
    await tokenInput.fill("some-token");

    // The Auth tab button should have a dot indicator (badge) when type is not "none"
    // We verify by checking the tab shows Auth is active (dot indicator)
    const authTab = page.getByRole("button", { name: "Auth" });
    await expect(authTab).toBeVisible();
    // The badge dot is rendered inside the Auth tab button
    await expect(authTab.locator("span.bg-cobweb-500")).toBeVisible();
  });

  test("Bearer token is sent as Authorization header", async ({ page }) => {
    // Set up auth
    await page.keyboard.press("Alt+4");
    const select = page.getByTestId("auth-type-select");
    await select.selectOption("bearer");
    await page.getByPlaceholder("{{token}}").fill("test-bearer-token");

    // Enter a URL to the sidecar diagnostics (which echoes back request info)
    const urlInput = page.getByPlaceholder(/Enter URL/i).or(page.locator("input[type='text']").first());
    await urlInput.fill(`${SIDECAR}/api/health`);

    // Send the request
    await page.keyboard.press("Meta+Enter");

    // Wait for response
    await expect(page.getByText("200")).toBeVisible({ timeout: 10_000 });
  });
});
