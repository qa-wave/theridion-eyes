import { test, expect } from "@playwright/test";

test.describe("GraphQL modal", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });
  });

  test("opens GraphQL modal via command palette", async ({ page }) => {
    // Open command palette with Cmd+K
    await page.keyboard.press("Meta+k");
    await expect(page.getByPlaceholder(/Type a command/i)).toBeVisible();

    // Type "GraphQL" and select the action
    await page.getByPlaceholder(/Type a command/i).fill("Open GraphQL");
    await page.getByText("Open GraphQL", { exact: false }).first().click();

    // Modal should be open with the GQL badge and URL input
    await expect(page.getByText("GraphQL", { exact: true })).toBeVisible();
    await expect(
      page.getByPlaceholder("https://api.example.com/graphql"),
    ).toBeVisible();
  });

  test("has query editor with default content", async ({ page }) => {
    await page.keyboard.press("Meta+k");
    await page.getByPlaceholder(/Type a command/i).fill("Open GraphQL");
    await page.getByText("Open GraphQL", { exact: false }).first().click();

    // The modal should show the Query section label
    await expect(page.getByText("Query", { exact: true })).toBeVisible();
    // Variables and Headers sections should also be present
    await expect(page.getByText("Variables", { exact: true })).toBeVisible();
    await expect(page.getByText("Headers", { exact: true })).toBeVisible();
  });

  test("schema introspection button exists and is initially disabled", async ({
    page,
  }) => {
    await page.keyboard.press("Meta+k");
    await page.getByPlaceholder(/Type a command/i).fill("Open GraphQL");
    await page.getByText("Open GraphQL", { exact: false }).first().click();

    // Schema button should exist but be disabled when URL is empty
    const schemaBtn = page.getByRole("button", { name: "Schema" });
    await expect(schemaBtn).toBeVisible();
    await expect(schemaBtn).toBeDisabled();

    // Enter a URL — schema button should become enabled
    await page
      .getByPlaceholder("https://api.example.com/graphql")
      .fill("http://localhost:1234/graphql");
    await expect(schemaBtn).toBeEnabled();
  });

  test("run button is disabled without URL and query", async ({ page }) => {
    await page.keyboard.press("Meta+k");
    await page.getByPlaceholder(/Type a command/i).fill("Open GraphQL");
    await page.getByText("Open GraphQL", { exact: false }).first().click();

    const runBtn = page.getByRole("button", { name: "Run" });
    await expect(runBtn).toBeDisabled();

    // Fill URL only — still disabled if query is somehow empty? No, default
    // query exists ("query { __typename }"), so once URL is filled it enables.
    await page
      .getByPlaceholder("https://api.example.com/graphql")
      .fill("http://localhost:1234/graphql");
    await expect(runBtn).toBeEnabled();
  });

  test("response tab shows placeholder when no query has been run", async ({
    page,
  }) => {
    await page.keyboard.press("Meta+k");
    await page.getByPlaceholder(/Type a command/i).fill("Open GraphQL");
    await page.getByText("Open GraphQL", { exact: false }).first().click();

    // Response and Schema tabs should exist
    await expect(page.getByRole("button", { name: "Response" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Schema" }).nth(0),
    ).toBeVisible();

    // Placeholder text in response area
    await expect(page.getByText("Run a query to see results")).toBeVisible();
  });

  test("closes modal with X button", async ({ page }) => {
    await page.keyboard.press("Meta+k");
    await page.getByPlaceholder(/Type a command/i).fill("Open GraphQL");
    await page.getByText("Open GraphQL", { exact: false }).first().click();

    await expect(page.getByText("GraphQL", { exact: true })).toBeVisible();

    // Close via X button (the close button in the header)
    await page
      .locator("button")
      .filter({ has: page.locator("svg.lucide-x") })
      .first()
      .click();

    // Modal should disappear
    await expect(
      page.getByPlaceholder("https://api.example.com/graphql"),
    ).toBeHidden();
  });
});
