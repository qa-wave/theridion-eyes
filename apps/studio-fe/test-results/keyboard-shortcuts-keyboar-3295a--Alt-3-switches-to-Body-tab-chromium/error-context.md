# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: keyboard-shortcuts.spec.ts >> keyboard shortcuts >> Alt+3 switches to Body tab
- Location: tests/e2e/keyboard-shortcuts.spec.ts:84:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('Body', { exact: true }).or(getByText('Content-Type'))
Expected: visible
Error: strict mode violation: getByText('Body', { exact: true }).or(getByText('Content-Type')) resolved to 2 elements:
    1) <button type="button" class="relative h-8 rounded-lg px-3 text-[11px] font-medium transition-all duration-150 bg-white/[0.08] text-neutral-100 shadow-sm">Body</button> aka getByRole('button', { name: 'Body' })
    2) <p class="text-[11px] uppercase tracking-wider text-neutral-500">Body</p> aka getByRole('paragraph').filter({ hasText: /^Body$/ })

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByText('Body', { exact: true }).or(getByText('Content-Type'))

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
          - generic [ref=e225]:
            - paragraph [ref=e226]: Body
            - generic [ref=e227]:
              - button "Raw" [ref=e228] [cursor=pointer]
              - button "Form Data" [ref=e229] [cursor=pointer]
              - button "URL Encoded" [ref=e230] [cursor=pointer]
          - generic [ref=e231]:
            - button "JSON" [ref=e232] [cursor=pointer]
            - button "XML" [ref=e233] [cursor=pointer]
            - button "Text" [ref=e234] [cursor=pointer]
            - button "HTML" [ref=e235] [cursor=pointer]
            - button "YAML" [ref=e236] [cursor=pointer]
            - button "GraphQL" [ref=e237] [cursor=pointer]
            - button "Format" [ref=e239] [cursor=pointer]
            - button "Minify" [ref=e240] [cursor=pointer]
            - button "Snippets" [ref=e242] [cursor=pointer]:
              - text: Snippets
              - img [ref=e243]
          - generic [ref=e249]: Loading editor…
          - paragraph [ref=e250]: Add a JSON or XML request body. Switch to Form Data mode for key-value pairs.
      - generic [ref=e255]:
        - img [ref=e257]
        - paragraph [ref=e260]: No response yet
        - paragraph [ref=e261]: Hit Send or press ⌘⏎
  - contentinfo [ref=e263]:
    - button "sidecar v0.0.1 · 4m · 0m" [ref=e265] [cursor=pointer]:
      - generic [ref=e269]: sidecar v0.0.1
      - generic [ref=e270]: · 4m
      - generic [ref=e271]: · 0m
    - button "No env" [ref=e272] [cursor=pointer]:
      - generic [ref=e273]: No env
    - generic [ref=e274]:
      - button "Network Console" [ref=e275] [cursor=pointer]:
        - img [ref=e276]
      - button "Settings" [ref=e278] [cursor=pointer]:
        - img [ref=e279]
      - generic [ref=e282]: v0.0.1
```

# Test source

```ts
  1   | import { test, expect } from "@playwright/test";
  2   | 
  3   | test.describe("keyboard shortcuts", () => {
  4   |   test.beforeEach(async ({ page }) => {
  5   |     await page.goto("/");
  6   |     await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });
  7   |   });
  8   | 
  9   |   test("Cmd+T opens a new tab", async ({ page }) => {
  10  |     // Count initial tabs (there's always at least one)
  11  |     const initialTabs = await page.locator("[data-tab-id]").or(page.locator("button").filter({ hasText: /Untitled/ })).count();
  12  | 
  13  |     await page.keyboard.press("Meta+t");
  14  | 
  15  |     // Should have one more tab now
  16  |     const newTabs = await page.locator("[data-tab-id]").or(page.locator("button").filter({ hasText: /Untitled/ })).count();
  17  |     expect(newTabs).toBeGreaterThan(initialTabs);
  18  |   });
  19  | 
  20  |   test("Cmd+W closes the active tab", async ({ page }) => {
  21  |     // Open a second tab first
  22  |     await page.keyboard.press("Meta+t");
  23  |     const tabsAfterOpen = await page.locator("[data-tab-id]").or(page.locator("button").filter({ hasText: /Untitled/ })).count();
  24  | 
  25  |     await page.keyboard.press("Meta+w");
  26  | 
  27  |     const tabsAfterClose = await page.locator("[data-tab-id]").or(page.locator("button").filter({ hasText: /Untitled/ })).count();
  28  |     expect(tabsAfterClose).toBeLessThan(tabsAfterOpen);
  29  |   });
  30  | 
  31  |   test("Cmd+K opens command palette", async ({ page }) => {
  32  |     await page.keyboard.press("Meta+k");
  33  |     await expect(page.getByPlaceholder(/Type a command/i)).toBeVisible();
  34  |   });
  35  | 
  36  |   test("Cmd+K toggles command palette closed", async ({ page }) => {
  37  |     await page.keyboard.press("Meta+k");
  38  |     await expect(page.getByPlaceholder(/Type a command/i)).toBeVisible();
  39  | 
  40  |     await page.keyboard.press("Meta+k");
  41  |     await expect(page.getByPlaceholder(/Type a command/i)).toBeHidden();
  42  |   });
  43  | 
  44  |   test("Cmd+, opens settings", async ({ page }) => {
  45  |     await page.keyboard.press("Meta+,");
  46  |     await expect(page.getByRole("button", { name: "General", exact: true })).toBeVisible();
  47  |     await expect(page.getByRole("button", { name: "About", exact: true })).toBeVisible();
  48  |   });
  49  | 
  50  |   test("Cmd+Enter sends request", async ({ page }) => {
  51  |     // The send button should work even without URL (will likely error)
  52  |     // We just verify the action triggers by watching for response panel change
  53  |     const sendBtn = page.getByRole("button", { name: "Send" });
  54  |     await expect(sendBtn).toBeVisible();
  55  | 
  56  |     // Enter a valid URL first
  57  |     const urlInput = page.getByPlaceholder(/Enter URL/i).or(page.locator("input[type='text']").first());
  58  |     await urlInput.fill("http://127.0.0.1:8766/api/health");
  59  | 
  60  |     await page.keyboard.press("Meta+Enter");
  61  | 
  62  |     // Should get a response (200 from health endpoint)
  63  |     await expect(page.getByText("200")).toBeVisible({ timeout: 10_000 });
  64  |   });
  65  | 
  66  |   test("Alt+1 switches to Params tab", async ({ page }) => {
  67  |     // First switch away from Params
  68  |     await page.keyboard.press("Alt+2");
  69  |     await expect(page.getByText("Headers", { exact: false })).toBeVisible();
  70  | 
  71  |     // Switch back to Params
  72  |     await page.keyboard.press("Alt+1");
  73  |     await expect(page.getByText("Query parameters", { exact: true })).toBeVisible();
  74  |   });
  75  | 
  76  |   test("Alt+2 switches to Headers tab", async ({ page }) => {
  77  |     await page.keyboard.press("Alt+2");
  78  |     // Headers view has table/raw mode toggle
  79  |     await expect(
  80  |       page.getByRole("button", { name: /Table/i }).or(page.getByText("Table")),
  81  |     ).toBeVisible();
  82  |   });
  83  | 
  84  |   test("Alt+3 switches to Body tab", async ({ page }) => {
  85  |     await page.keyboard.press("Alt+3");
  86  |     // Body tab shows content-type preset buttons or an editor
  87  |     await expect(
  88  |       page.getByText("Body", { exact: true }).or(page.getByText("Content-Type")),
> 89  |     ).toBeVisible();
      |       ^ Error: expect(locator).toBeVisible() failed
  90  |   });
  91  | 
  92  |   test("Alt+4 switches to Auth tab", async ({ page }) => {
  93  |     await page.keyboard.press("Alt+4");
  94  |     await expect(page.getByText("Type", { exact: true })).toBeVisible();
  95  |     await expect(page.getByTestId("auth-type-select")).toBeVisible();
  96  |   });
  97  | 
  98  |   test("Escape closes command palette", async ({ page }) => {
  99  |     await page.keyboard.press("Meta+k");
  100 |     await expect(page.getByPlaceholder(/Type a command/i)).toBeVisible();
  101 | 
  102 |     await page.keyboard.press("Escape");
  103 |     await expect(page.getByPlaceholder(/Type a command/i)).toBeHidden();
  104 |   });
  105 | 
  106 |   test("Escape closes settings modal", async ({ page }) => {
  107 |     await page.keyboard.press("Meta+,");
  108 |     await expect(page.getByRole("button", { name: "General", exact: true })).toBeVisible();
  109 | 
  110 |     await page.keyboard.press("Escape");
  111 |     await expect(page.getByRole("button", { name: "General", exact: true })).toBeHidden();
  112 |   });
  113 | });
  114 | 
```