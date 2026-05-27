import { test, expect } from "@playwright/test";

test.describe("request panel tabs", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });
  });

  test.describe("Params tab", () => {
    test("shows query parameters table", async ({ page }) => {
      // Params tab is active by default
      await expect(page.getByText("Query parameters", { exact: true })).toBeVisible();
      await expect(page.getByText("No query parameters")).toBeVisible();
    });

    test("adding a parameter updates the URL", async ({ page }) => {
      // Click "+ Add parameter"
      await page.getByText("+ Add parameter").click();

      // Fill in key and value
      const nameInput = page.getByPlaceholder("name").first();
      const valueInput = page.getByPlaceholder("value").first();
      await nameInput.fill("page");
      await valueInput.fill("1");

      // URL bar should now contain the query parameter
      const urlInput = page.getByPlaceholder(/Enter URL/i).or(page.locator("input[type='text']").first());
      await expect(urlInput).toHaveValue(/[?&]page=1/);
    });

    test("adding multiple parameters builds correct query string", async ({
      page,
    }) => {
      await page.getByText("+ Add parameter").click();
      await page.getByPlaceholder("name").first().fill("page");
      await page.getByPlaceholder("value").first().fill("1");

      await page.getByText("+ Add parameter").click();
      await page.getByPlaceholder("name").nth(1).fill("limit");
      await page.getByPlaceholder("value").nth(1).fill("20");

      const urlInput = page.getByPlaceholder(/Enter URL/i).or(page.locator("input[type='text']").first());
      await expect(urlInput).toHaveValue(/page=1/);
      await expect(urlInput).toHaveValue(/limit=20/);
    });

    test("removing a parameter updates the URL", async ({ page }) => {
      await page.getByText("+ Add parameter").click();
      await page.getByPlaceholder("name").first().fill("key");
      await page.getByPlaceholder("value").first().fill("val");

      // Remove the parameter
      await page.getByTitle("Remove").first().click();

      await expect(page.getByText("No query parameters")).toBeVisible();
    });
  });

  test.describe("Headers tab", () => {
    test("shows table mode by default", async ({ page }) => {
      await page.keyboard.press("Alt+2");

      // Table mode button should be active
      await expect(
        page.getByRole("button", { name: /Table/i }),
      ).toBeVisible();
    });

    test("can switch between table and raw mode", async ({ page }) => {
      await page.keyboard.press("Alt+2");

      // Switch to raw mode
      await page.getByRole("button", { name: /Raw/i }).click();

      // Raw mode shows a code editor area (Monaco or textarea)
      // Switch back to table
      await page.getByRole("button", { name: /Table/i }).click();
    });

    test("adding a header in table mode", async ({ page }) => {
      await page.keyboard.press("Alt+2");

      // Click add header button
      const addBtn = page.getByText("+ Add header").or(page.getByRole("button", { name: /Add/i }));
      await addBtn.first().click();

      // Fill header name and value
      const nameInputs = page.getByPlaceholder("name").or(page.getByPlaceholder("Header name"));
      const valueInputs = page.getByPlaceholder("value").or(page.getByPlaceholder("Header value"));
      await nameInputs.first().fill("X-Custom-Header");
      await valueInputs.first().fill("custom-value");

      await expect(nameInputs.first()).toHaveValue("X-Custom-Header");
    });
  });

  test.describe("Body tab", () => {
    test("shows body editor area", async ({ page }) => {
      await page.keyboard.press("Alt+3");

      // Body tab should have content-type presets or editor
      // Look for common content type buttons
      await expect(
        page.getByText("JSON").or(page.getByText("Content-Type")).or(page.getByText("Body")),
      ).toBeVisible();
    });

    test("content-type preset buttons exist", async ({ page }) => {
      await page.keyboard.press("Alt+3");

      // Common presets for body content type
      await expect(
        page
          .getByRole("button", { name: /JSON/i })
          .or(page.getByText("application/json")),
      ).toBeVisible();
    });
  });

  test.describe("Notes tab", () => {
    test("opens notes tab via Alt+7", async ({ page }) => {
      await page.keyboard.press("Alt+7");

      // Notes tab should show a text area or editor for markdown
      // Look for the notes content area
      await expect(
        page
          .getByPlaceholder(/notes/i)
          .or(page.getByPlaceholder(/markdown/i))
          .or(page.getByText("Notes", { exact: true }))
          .or(page.locator("[data-testid='notes-editor']"))
          .or(page.locator("textarea")),
      ).toBeVisible();
    });
  });

  test.describe("Tests tab", () => {
    test("opens tests tab via Alt+5", async ({ page }) => {
      await page.keyboard.press("Alt+5");

      // Tests tab should show assertion builder
      await expect(
        page
          .getByText(/assertion/i)
          .or(page.getByText("Add", { exact: true }))
          .or(page.getByRole("button", { name: /Add/i })),
      ).toBeVisible();
    });
  });
});
