# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: request-panel.spec.ts >> request panel tabs >> Params tab >> adding multiple parameters builds correct query string
- Location: tests/e2e/request-panel.spec.ts:31:5

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.fill: Test timeout of 30000ms exceeded.
Call log:
  - waiting for getByPlaceholder('name').first()

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
          - button "+ Add parameter" [active] [ref=e236] [cursor=pointer]
      - generic [ref=e241]:
        - img [ref=e243]
        - paragraph [ref=e246]: No response yet
        - paragraph [ref=e247]: Hit Send or press ⌘⏎
  - contentinfo [ref=e249]:
    - button "sidecar v0.0.1 · 5m · 0m" [ref=e251] [cursor=pointer]:
      - generic [ref=e255]: sidecar v0.0.1
      - generic [ref=e256]: · 5m
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
  1   | import { test, expect } from "@playwright/test";
  2   | 
  3   | test.describe("request panel tabs", () => {
  4   |   test.beforeEach(async ({ page }) => {
  5   |     await page.goto("/");
  6   |     await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });
  7   |   });
  8   | 
  9   |   test.describe("Params tab", () => {
  10  |     test("shows query parameters table", async ({ page }) => {
  11  |       // Params tab is active by default
  12  |       await expect(page.getByText("Query parameters", { exact: true })).toBeVisible();
  13  |       await expect(page.getByText("No query parameters")).toBeVisible();
  14  |     });
  15  | 
  16  |     test("adding a parameter updates the URL", async ({ page }) => {
  17  |       // Click "+ Add parameter"
  18  |       await page.getByText("+ Add parameter").click();
  19  | 
  20  |       // Fill in key and value
  21  |       const nameInput = page.getByPlaceholder("name").first();
  22  |       const valueInput = page.getByPlaceholder("value").first();
  23  |       await nameInput.fill("page");
  24  |       await valueInput.fill("1");
  25  | 
  26  |       // URL bar should now contain the query parameter
  27  |       const urlInput = page.getByPlaceholder(/Enter URL/i).or(page.locator("input[type='text']").first());
  28  |       await expect(urlInput).toHaveValue(/[?&]page=1/);
  29  |     });
  30  | 
  31  |     test("adding multiple parameters builds correct query string", async ({
  32  |       page,
  33  |     }) => {
  34  |       await page.getByText("+ Add parameter").click();
> 35  |       await page.getByPlaceholder("name").first().fill("page");
      |                                                   ^ Error: locator.fill: Test timeout of 30000ms exceeded.
  36  |       await page.getByPlaceholder("value").first().fill("1");
  37  | 
  38  |       await page.getByText("+ Add parameter").click();
  39  |       await page.getByPlaceholder("name").nth(1).fill("limit");
  40  |       await page.getByPlaceholder("value").nth(1).fill("20");
  41  | 
  42  |       const urlInput = page.getByPlaceholder(/Enter URL/i).or(page.locator("input[type='text']").first());
  43  |       await expect(urlInput).toHaveValue(/page=1/);
  44  |       await expect(urlInput).toHaveValue(/limit=20/);
  45  |     });
  46  | 
  47  |     test("removing a parameter updates the URL", async ({ page }) => {
  48  |       await page.getByText("+ Add parameter").click();
  49  |       await page.getByPlaceholder("name").first().fill("key");
  50  |       await page.getByPlaceholder("value").first().fill("val");
  51  | 
  52  |       // Remove the parameter
  53  |       await page.getByTitle("Remove").first().click();
  54  | 
  55  |       await expect(page.getByText("No query parameters")).toBeVisible();
  56  |     });
  57  |   });
  58  | 
  59  |   test.describe("Headers tab", () => {
  60  |     test("shows table mode by default", async ({ page }) => {
  61  |       await page.keyboard.press("Alt+2");
  62  | 
  63  |       // Table mode button should be active
  64  |       await expect(
  65  |         page.getByRole("button", { name: /Table/i }),
  66  |       ).toBeVisible();
  67  |     });
  68  | 
  69  |     test("can switch between table and raw mode", async ({ page }) => {
  70  |       await page.keyboard.press("Alt+2");
  71  | 
  72  |       // Switch to raw mode
  73  |       await page.getByRole("button", { name: /Raw/i }).click();
  74  | 
  75  |       // Raw mode shows a code editor area (Monaco or textarea)
  76  |       // Switch back to table
  77  |       await page.getByRole("button", { name: /Table/i }).click();
  78  |     });
  79  | 
  80  |     test("adding a header in table mode", async ({ page }) => {
  81  |       await page.keyboard.press("Alt+2");
  82  | 
  83  |       // Click add header button
  84  |       const addBtn = page.getByText("+ Add header").or(page.getByRole("button", { name: /Add/i }));
  85  |       await addBtn.first().click();
  86  | 
  87  |       // Fill header name and value
  88  |       const nameInputs = page.getByPlaceholder("name").or(page.getByPlaceholder("Header name"));
  89  |       const valueInputs = page.getByPlaceholder("value").or(page.getByPlaceholder("Header value"));
  90  |       await nameInputs.first().fill("X-Custom-Header");
  91  |       await valueInputs.first().fill("custom-value");
  92  | 
  93  |       await expect(nameInputs.first()).toHaveValue("X-Custom-Header");
  94  |     });
  95  |   });
  96  | 
  97  |   test.describe("Body tab", () => {
  98  |     test("shows body editor area", async ({ page }) => {
  99  |       await page.keyboard.press("Alt+3");
  100 | 
  101 |       // Body tab should have content-type presets or editor
  102 |       // Look for common content type buttons
  103 |       await expect(
  104 |         page.getByText("JSON").or(page.getByText("Content-Type")).or(page.getByText("Body")),
  105 |       ).toBeVisible();
  106 |     });
  107 | 
  108 |     test("content-type preset buttons exist", async ({ page }) => {
  109 |       await page.keyboard.press("Alt+3");
  110 | 
  111 |       // Common presets for body content type
  112 |       await expect(
  113 |         page
  114 |           .getByRole("button", { name: /JSON/i })
  115 |           .or(page.getByText("application/json")),
  116 |       ).toBeVisible();
  117 |     });
  118 |   });
  119 | 
  120 |   test.describe("Notes tab", () => {
  121 |     test("opens notes tab via Alt+7", async ({ page }) => {
  122 |       await page.keyboard.press("Alt+7");
  123 | 
  124 |       // Notes tab should show a text area or editor for markdown
  125 |       // Look for the notes content area
  126 |       await expect(
  127 |         page
  128 |           .getByPlaceholder(/notes/i)
  129 |           .or(page.getByPlaceholder(/markdown/i))
  130 |           .or(page.getByText("Notes", { exact: true }))
  131 |           .or(page.locator("[data-testid='notes-editor']"))
  132 |           .or(page.locator("textarea")),
  133 |       ).toBeVisible();
  134 |     });
  135 |   });
```