import { test, expect } from "@playwright/test";
import { TEST_SIDECAR_PORT } from "../../playwright.config";

const SIDECAR = `http://127.0.0.1:${TEST_SIDECAR_PORT}`;

/**
 * Verifies the file-based collection store end-to-end:
 *   1. seed a collection via the sidecar API
 *   2. open the desktop UI and confirm it appears in the sidebar
 *   3. create a folder via the API and watch the tree update on refresh
 *
 * We seed via the API rather than the UI because the SavePopover requires
 * filling URL + body + dialog flow, which is covered separately in
 * save.spec.ts. Here we test that the sidebar reflects the stored truth.
 */
test.describe("collections", () => {
  test.beforeEach(async ({ request }) => {
    // Drain leftover collections from previous tests in this run. The
    // global setup only fires once; per-test isolation is via DELETE.
    const summaries = await request
      .get(`${SIDECAR}/api/collections`)
      .then((r) => r.json());
    for (const s of summaries) {
      await request.delete(`${SIDECAR}/api/collections/${s.id}`);
    }
  });

  test("seeded collection shows up in sidebar after refresh", async ({
    page,
    request,
  }) => {
    const created = await request
      .post(`${SIDECAR}/api/collections`, { data: { name: "GitHub API" } })
      .then((r) => r.json());
    expect(created.id).toBeTruthy();

    await page.goto("/");
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });

    // Wait for the collection to render. The refresh runs on mount once
    // the sidecar reports healthy.
    await expect(page.getByText("GitHub API")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/No collections yet/)).toBeHidden();
  });

  test("folder created via API appears nested under its collection", async ({
    page,
    request,
  }) => {
    const coll = await request
      .post(`${SIDECAR}/api/collections`, { data: { name: "API v1" } })
      .then((r) => r.json());
    await request.post(`${SIDECAR}/api/collections/${coll.id}/folders`, {
      data: { name: "Repositories" },
    });
    // Save a request inside the folder so the leaf renders too.
    const folderId = await request
      .get(`${SIDECAR}/api/collections/${coll.id}`)
      .then((r) => r.json())
      .then((c) => c.items[0].id);
    await request.post(`${SIDECAR}/api/collections/${coll.id}/requests`, {
      data: {
        name: "List repos",
        method: "GET",
        url: "https://api.example.com/repos",
        parent_folder_id: folderId,
      },
    });

    await page.goto("/");
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });

    // Sidebar should show: API v1 → Repositories → List repos.
    await expect(page.getByText("API v1")).toBeVisible();
    await expect(page.getByText("Repositories")).toBeVisible();
    await expect(page.getByText("List repos")).toBeVisible();
  });
});
