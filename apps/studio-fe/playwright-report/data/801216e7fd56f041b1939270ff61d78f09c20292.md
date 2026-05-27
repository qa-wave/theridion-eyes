# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: history.spec.ts >> history panel >> history shows method and status for each entry
- Location: tests/e2e/history.spec.ts:37:3

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.fill: Test timeout of 30000ms exceeded.
Call log:
  - waiting for getByPlaceholder(/Enter URL/i).or(locator('input[type=\'text\']').first())

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - generic [ref=e5]:
    - button [ref=e7] [cursor=pointer]:
      - img [ref=e8]
    - button [ref=e11] [cursor=pointer]:
      - img [ref=e12]
    - button [ref=e17] [cursor=pointer]:
      - img [ref=e18]
    - button [ref=e25] [cursor=pointer]:
      - img [ref=e26]
  - complementary [ref=e29]:
    - heading "Theridion" [level=1] [ref=e31]
    - generic [ref=e32]:
      - generic [ref=e33]: Collections
      - button [ref=e35] [cursor=pointer]:
        - img [ref=e36]
      - button [ref=e42] [cursor=pointer]:
        - img [ref=e43]
      - button [ref=e47] [cursor=pointer]:
        - img [ref=e48]
      - button [ref=e50] [cursor=pointer]:
        - img [ref=e51]
    - generic [ref=e55]:
      - img
      - searchbox "Filter…" [ref=e56]
    - generic [ref=e58]:
      - generic [ref=e59]:
        - button [ref=e60] [cursor=pointer]:
          - img [ref=e61]
        - img [ref=e63]
        - button "API v1" [ref=e65] [cursor=pointer]
        - generic [ref=e66]: "1"
        - button "Rename" [ref=e67] [cursor=pointer]:
          - img [ref=e68]
        - button "New folder at root" [ref=e71] [cursor=pointer]:
          - img [ref=e72]
        - button "Run collection" [ref=e74] [cursor=pointer]:
          - img [ref=e75]
        - button "Export as cURL" [ref=e77] [cursor=pointer]:
          - img [ref=e78]
        - button "Export as Postman" [ref=e80] [cursor=pointer]:
          - img [ref=e81]
        - button "View Statistics" [ref=e84] [cursor=pointer]:
          - img [ref=e85]
        - button "Generate Docs" [ref=e87] [cursor=pointer]:
          - img [ref=e88]
        - button "Delete collection" [ref=e91] [cursor=pointer]:
          - img [ref=e92]
      - generic [ref=e96]:
        - generic [ref=e97]:
          - button [ref=e98] [cursor=pointer]:
            - img [ref=e99]
          - img [ref=e101]
          - button "Repositories" [ref=e103] [cursor=pointer]
          - generic [ref=e104]: "1"
          - button "Rename" [ref=e105] [cursor=pointer]:
            - img [ref=e106]
          - button "New subfolder" [ref=e109] [cursor=pointer]:
            - img [ref=e110]
          - button "Delete folder" [ref=e112] [cursor=pointer]:
            - img [ref=e113]
        - generic [ref=e117]:
          - button "GET List repos" [ref=e118] [cursor=pointer]:
            - generic [ref=e119]: GET
            - generic [ref=e120]: List repos
          - button "Add to favorites" [ref=e121] [cursor=pointer]:
            - img [ref=e122]
          - button "Rename" [ref=e124] [cursor=pointer]:
            - img [ref=e125]
          - button "Delete request" [ref=e128] [cursor=pointer]:
            - img [ref=e129]
    - generic [ref=e132]:
      - button "Collapse" [ref=e133] [cursor=pointer]:
        - img [ref=e134]
        - generic [ref=e136]: Collapse
      - button "Shortcuts ⌘?" [ref=e137] [cursor=pointer]
  - main [ref=e138]:
    - generic [ref=e139]:
      - button "GET Untitled Close tab" [ref=e141] [cursor=pointer]:
        - generic [ref=e142]: GET
        - generic [ref=e143]: Untitled
        - button "Close tab" [ref=e144]:
          - img [ref=e145]
      - generic [ref=e148]:
        - button "New request (Cmd+T)" [ref=e149] [cursor=pointer]:
          - img [ref=e150]
        - button "Cmd+K" [ref=e151] [cursor=pointer]:
          - img [ref=e152]
          - generic [ref=e154]: Cmd+K
        - button "More" [ref=e156] [cursor=pointer]:
          - img [ref=e157]
          - generic [ref=e161]: More
        - button "History" [ref=e162] [cursor=pointer]:
          - img [ref=e163]
          - generic [ref=e166]: History
        - button "No env" [ref=e169] [cursor=pointer]:
          - img [ref=e170]
          - generic [ref=e174]: No env
          - img [ref=e175]
    - generic [ref=e179]:
      - generic [ref=e180]:
        - generic [ref=e182]:
          - combobox [ref=e183]:
            - option "GET" [selected]
            - option "POST"
            - option "PUT"
            - option "PATCH"
            - option "DELETE"
            - option "HEAD"
            - option "OPTIONS"
          - generic: ▾
        - textbox "https://api.example.com/v1/resource" [ref=e186]
      - generic [ref=e187]:
        - button "Save" [disabled] [ref=e188]:
          - img [ref=e189]
          - text: Save
        - button "Save to\\u2026 (\\u2318\\u21E7S)" [disabled] [ref=e193]:
          - img [ref=e194]
      - button "cURL" [disabled] [ref=e196]:
        - img [ref=e197]
        - text: cURL
      - button "Share" [disabled] [ref=e202]
      - generic [ref=e204]:
        - img
        - combobox [ref=e205]:
          - option "No environment" [selected]
          - option "T"
        - generic: ▾
      - button "Send" [disabled] [ref=e206]:
        - img [ref=e207]
        - text: Send
    - generic [ref=e210]:
      - generic [ref=e212]:
        - generic [ref=e213]:
          - button "Params" [ref=e214] [cursor=pointer]
          - button "Headers" [ref=e215] [cursor=pointer]
          - button "Body" [ref=e216] [cursor=pointer]
          - button "Auth" [ref=e217] [cursor=pointer]
          - button "Certs" [ref=e218] [cursor=pointer]
          - button "Tests" [ref=e219] [cursor=pointer]
          - button "Scripts" [ref=e220] [cursor=pointer]
          - button "Retry" [ref=e221] [cursor=pointer]
          - button "Notes" [ref=e222] [cursor=pointer]
        - generic [ref=e224]:
          - paragraph [ref=e225]: Query parameters
          - table [ref=e227]:
            - rowgroup [ref=e228]:
              - row "Name Value" [ref=e229]:
                - columnheader "Name" [ref=e230]
                - columnheader "Value" [ref=e231]
                - columnheader [ref=e232]
            - rowgroup [ref=e233]:
              - row "No query parameters" [ref=e234]:
                - cell "No query parameters" [ref=e235]
          - button "+ Add parameter" [ref=e236] [cursor=pointer]
      - generic [ref=e241]:
        - img [ref=e243]
        - paragraph [ref=e246]: No response yet
        - paragraph [ref=e247]: Hit Send or press ⌘⏎
  - contentinfo [ref=e249]:
    - button "sidecar v0.0.1 · 2m · 0m" [ref=e251] [cursor=pointer]:
      - generic [ref=e255]: sidecar v0.0.1
      - generic [ref=e256]: · 2m
      - generic [ref=e257]: · 0m
    - button "No env" [ref=e258] [cursor=pointer]:
      - generic [ref=e259]: No env
    - generic [ref=e260]:
      - button "Network Console" [ref=e261] [cursor=pointer]:
        - img [ref=e262]
      - button "Settings" [ref=e264] [cursor=pointer]:
        - img [ref=e265]
      - generic [ref=e268]: v0.0.1
```

# Test source

```ts
  1  | import { test, expect } from "@playwright/test";
  2  | import { TEST_SIDECAR_PORT } from "../../playwright.config";
  3  | 
  4  | const SIDECAR = `http://127.0.0.1:${TEST_SIDECAR_PORT}`;
  5  | 
  6  | test.describe("history panel", () => {
  7  |   test.beforeEach(async ({ page, request }) => {
  8  |     // Clear history before each test
  9  |     try {
  10 |       await request.delete(`${SIDECAR}/api/history`);
  11 |     } catch {
  12 |       // Endpoint might not exist yet — ignore
  13 |     }
  14 |     await page.goto("/");
  15 |     await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });
  16 |   });
  17 | 
  18 |   test("sent request appears in history panel", async ({ page }) => {
  19 |     // Enter a URL targeting the sidecar's own health endpoint (will succeed)
  20 |     const urlInput = page.getByPlaceholder(/Enter URL/i).or(page.locator("input[type='text']").first());
  21 |     await urlInput.fill(`${SIDECAR}/api/health`);
  22 | 
  23 |     // Send the request
  24 |     await page.getByRole("button", { name: "Send" }).click();
  25 | 
  26 |     // Wait for response to appear (status badge)
  27 |     await expect(page.getByText("200")).toBeVisible({ timeout: 10_000 });
  28 | 
  29 |     // Open history panel via Cmd+Shift+H
  30 |     await page.keyboard.press("Meta+Shift+h");
  31 | 
  32 |     // History panel should be visible with the entry
  33 |     await expect(page.getByText("History", { exact: true })).toBeVisible();
  34 |     await expect(page.getByText("/api/health")).toBeVisible({ timeout: 5_000 });
  35 |   });
  36 | 
  37 |   test("history shows method and status for each entry", async ({ page }) => {
  38 |     // Send a request
  39 |     const urlInput = page.getByPlaceholder(/Enter URL/i).or(page.locator("input[type='text']").first());
> 40 |     await urlInput.fill(`${SIDECAR}/api/health`);
     |                    ^ Error: locator.fill: Test timeout of 30000ms exceeded.
  41 |     await page.getByRole("button", { name: "Send" }).click();
  42 |     await expect(page.getByText("200")).toBeVisible({ timeout: 10_000 });
  43 | 
  44 |     // Open history
  45 |     await page.keyboard.press("Meta+Shift+h");
  46 |     await expect(page.getByText("History", { exact: true })).toBeVisible();
  47 | 
  48 |     // Should show GET method badge
  49 |     await expect(
  50 |       page.locator("[class*='history']").or(page.locator("div")).filter({ hasText: "GET" }).first(),
  51 |     ).toBeVisible();
  52 |   });
  53 | 
  54 |   test("clear history empties the list", async ({ page }) => {
  55 |     // Send a request first
  56 |     const urlInput = page.getByPlaceholder(/Enter URL/i).or(page.locator("input[type='text']").first());
  57 |     await urlInput.fill(`${SIDECAR}/api/health`);
  58 |     await page.getByRole("button", { name: "Send" }).click();
  59 |     await expect(page.getByText("200")).toBeVisible({ timeout: 10_000 });
  60 | 
  61 |     // Open history
  62 |     await page.keyboard.press("Meta+Shift+h");
  63 |     await expect(page.getByText("/api/health")).toBeVisible({ timeout: 5_000 });
  64 | 
  65 |     // Click clear button (trash icon in history header)
  66 |     await page.getByTitle("Clear history").click();
  67 | 
  68 |     // History should now show empty state
  69 |     await expect(page.getByText("No history yet")).toBeVisible();
  70 |   });
  71 | 
  72 |   test("toggle history panel open and closed", async ({ page }) => {
  73 |     const searchInput = page.getByPlaceholder("Search URL, method...");
  74 | 
  75 |     // Open history
  76 |     await page.keyboard.press("Meta+Shift+h");
  77 |     await expect(searchInput).toBeVisible();
  78 | 
  79 |     // Close it again with same shortcut
  80 |     await page.keyboard.press("Meta+Shift+h");
  81 |     await expect(searchInput).toBeHidden({ timeout: 3_000 });
  82 |   });
  83 | });
  84 | 
```