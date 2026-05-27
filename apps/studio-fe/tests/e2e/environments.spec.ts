import { test, expect } from "@playwright/test";
import { TEST_SIDECAR_PORT } from "../../playwright.config";

const SIDECAR = `http://127.0.0.1:${TEST_SIDECAR_PORT}`;

test.describe("environments", () => {
  test.beforeEach(async ({ request }) => {
    const list = await request
      .get(`${SIDECAR}/api/environments`)
      .then((r) => r.json());
    for (const e of list) {
      await request.delete(`${SIDECAR}/api/environments/${e.id}`);
    }
  });

  test("seeded env appears in the dropdown and selecting it sticks", async ({
    page,
    request,
  }) => {
    await request.post(`${SIDECAR}/api/environments`, {
      data: { name: "Production" },
    });

    await page.goto("/");
    await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });

    // Open env dropdown — it sits on the right of the tab bar.
    await page.getByTitle("No environment", { exact: true }).click();
    await expect(page.getByRole("menu")).toBeVisible();
    await page.getByRole("menu").getByText("Production").click();

    // Chip now shows the selected env name.
    await expect(page.getByRole("button", { name: /Production/ })).toBeVisible();
  });

  test("variables CRUD round-trips through the API", async ({ request }) => {
    // The full {{var}} substitution path is exhaustively covered by the
    // sidecar's pytest suite with mocked httpx; here we just smoke-test
    // the public CRUD that the modal drives.
    const env = await request
      .post(`${SIDECAR}/api/environments`, { data: { name: "T" } })
      .then((r) => r.json());
    await request.put(`${SIDECAR}/api/environments/${env.id}/variables`, {
      data: {
        variables: [
          { name: "host", value: "api.example.com", enabled: true },
          { name: "tok", value: "secret", enabled: false },
        ],
      },
    });
    const reread = await request
      .get(`${SIDECAR}/api/environments/${env.id}`)
      .then((r) => r.json());
    expect(reread.variables).toHaveLength(2);
    expect(reread.variables[0]).toMatchObject({
      name: "host",
      value: "api.example.com",
      enabled: true,
    });
    expect(reread.variables[1].enabled).toBe(false);
  });
});
