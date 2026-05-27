import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = path.resolve(
  __dirname,
  "../../../sidecar/tests/fixtures/calculator.wsdl",
);
const FIXTURE_URL = `file://${FIXTURE_PATH}`;

test.describe("SOAP modal", () => {
  test("inspect against fixture WSDL surfaces operations", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });

    // Open the modal via the command palette (SOAP/REST tabs are no longer in the bar).
    await page.keyboard.press("Meta+k");
    await page.getByPlaceholder(/Type a command/i).fill("SOAP");
    await page.getByText("SOAP Request").first().click();
    await expect(page.getByRole("dialog", { name: "SOAP / WSDL" })).toBeVisible();

    // Paste the fixture path and inspect.
    await page
      .getByPlaceholder(/example.com\/service\?wsdl/)
      .fill(FIXTURE_URL);
    await page.getByRole("button", { name: /Inspect/ }).click();

    // Service tree should populate with CalcService → CalcPort → Add+Subtract.
    // Operation names appear twice in the dialog (button in the tree +
    // header for the auto-selected one), so we target the buttons in the
    // tree by role to disambiguate.
    const dialog = page.getByRole("dialog", { name: "SOAP / WSDL" });
    await expect(
      dialog.getByText("CalcService", { exact: true }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(dialog.getByText("CalcPort", { exact: true })).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Add", exact: true }),
    ).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Subtract", exact: true }),
    ).toBeVisible();

    // Header shows the auto-selected operation with its SOAP action.
    await expect(dialog.getByText("http://example.com/calc/Add")).toBeVisible();
  });
});
