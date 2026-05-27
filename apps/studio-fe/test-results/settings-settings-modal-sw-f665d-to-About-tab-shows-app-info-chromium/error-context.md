# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: settings.spec.ts >> settings modal >> switching to About tab shows app info
- Location: tests/e2e/settings.spec.ts:71:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('v0.0.1')
Expected: visible
Error: strict mode violation: getByText('v0.0.1') resolved to 3 elements:
    1) <span class="text-neutral-300">sidecar v0.0.1</span> aka getByRole('button', { name: 'sidecar v0.0.1 · 7m · 0m' })
    2) <span class="font-mono text-[10px] text-neutral-600">v0.0.1</span> aka getByRole('contentinfo').getByText('v0.0.1', { exact: true })
    3) <p class="mt-0.5 font-mono text-[11px] text-neutral-600">v0.0.1</p> aka getByRole('paragraph').filter({ hasText: 'v0.0.1' })

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByText('v0.0.1')

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
      - generic [ref=e33]:
        - button [ref=e34] [cursor=pointer]:
          - img [ref=e35]
        - img [ref=e37]
        - generic [ref=e39]: Favorites
        - generic [ref=e40]: "1"
      - button "GET List repos" [ref=e42] [cursor=pointer]:
        - img [ref=e43]
        - generic [ref=e45]: GET
        - generic [ref=e46]: List repos
    - generic [ref=e47]:
      - generic [ref=e48]: Collections
      - button [ref=e50] [cursor=pointer]:
        - img [ref=e51]
      - button [ref=e57] [cursor=pointer]:
        - img [ref=e58]
      - button [ref=e62] [cursor=pointer]:
        - img [ref=e63]
      - button [ref=e65] [cursor=pointer]:
        - img [ref=e66]
    - generic [ref=e70]:
      - img
      - searchbox "Filter…" [ref=e71]
    - generic [ref=e73]:
      - generic [ref=e74]:
        - button [ref=e75] [cursor=pointer]:
          - img [ref=e76]
        - img [ref=e78]
        - button "API v1" [ref=e80] [cursor=pointer]
        - generic [ref=e81]: "1"
        - button "Rename" [ref=e82] [cursor=pointer]:
          - img [ref=e83]
        - button "New folder at root" [ref=e86] [cursor=pointer]:
          - img [ref=e87]
        - button "Run collection" [ref=e89] [cursor=pointer]:
          - img [ref=e90]
        - button "Export as cURL" [ref=e92] [cursor=pointer]:
          - img [ref=e93]
        - button "Export as Postman" [ref=e95] [cursor=pointer]:
          - img [ref=e96]
        - button "View Statistics" [ref=e99] [cursor=pointer]:
          - img [ref=e100]
        - button "Generate Docs" [ref=e102] [cursor=pointer]:
          - img [ref=e103]
        - button "Delete collection" [ref=e106] [cursor=pointer]:
          - img [ref=e107]
      - generic [ref=e111]:
        - generic [ref=e112]:
          - button [ref=e113] [cursor=pointer]:
            - img [ref=e114]
          - img [ref=e116]
          - button "Repositories" [ref=e118] [cursor=pointer]
          - generic [ref=e119]: "1"
          - button "Rename" [ref=e120] [cursor=pointer]:
            - img [ref=e121]
          - button "New subfolder" [ref=e124] [cursor=pointer]:
            - img [ref=e125]
          - button "Delete folder" [ref=e127] [cursor=pointer]:
            - img [ref=e128]
        - generic [ref=e132]:
          - button "GET List repos" [ref=e133] [cursor=pointer]:
            - generic [ref=e134]: GET
            - generic [ref=e135]: List repos
          - button "Remove from favorites" [ref=e136] [cursor=pointer]:
            - img [ref=e137]
          - button "Rename" [ref=e139] [cursor=pointer]:
            - img [ref=e140]
          - button "Delete request" [ref=e143] [cursor=pointer]:
            - img [ref=e144]
    - generic [ref=e147]:
      - button "Collapse" [ref=e148] [cursor=pointer]:
        - img [ref=e149]
        - generic [ref=e151]: Collapse
      - button "Shortcuts ⌘?" [ref=e152] [cursor=pointer]
  - main [ref=e153]:
    - generic [ref=e154]:
      - button "GET Untitled Close tab" [ref=e156] [cursor=pointer]:
        - generic [ref=e157]: GET
        - generic [ref=e158]: Untitled
        - button "Close tab" [ref=e159]:
          - img [ref=e160]
      - generic [ref=e163]:
        - button "New request (Cmd+T)" [ref=e164] [cursor=pointer]:
          - img [ref=e165]
        - button "Cmd+K" [ref=e166] [cursor=pointer]:
          - img [ref=e167]
          - generic [ref=e169]: Cmd+K
        - button "More" [ref=e171] [cursor=pointer]:
          - img [ref=e172]
          - generic [ref=e176]: More
        - button "History" [ref=e177] [cursor=pointer]:
          - img [ref=e178]
          - generic [ref=e181]: History
        - button "No env" [ref=e184] [cursor=pointer]:
          - img [ref=e185]
          - generic [ref=e189]: No env
          - img [ref=e190]
    - generic [ref=e194]:
      - generic [ref=e195]:
        - generic [ref=e197]:
          - combobox [ref=e198]:
            - option "GET" [selected]
            - option "POST"
            - option "PUT"
            - option "PATCH"
            - option "DELETE"
            - option "HEAD"
            - option "OPTIONS"
          - generic: ▾
        - textbox "https://api.example.com/v1/resource" [ref=e201]
      - generic [ref=e202]:
        - button "Save" [disabled] [ref=e203]:
          - img [ref=e204]
          - text: Save
        - button "Save to\\u2026 (\\u2318\\u21E7S)" [disabled] [ref=e208]:
          - img [ref=e209]
      - button "cURL" [disabled] [ref=e211]:
        - img [ref=e212]
        - text: cURL
      - button "Share" [disabled] [ref=e217]
      - generic [ref=e219]:
        - img
        - combobox [ref=e220]:
          - option "No environment" [selected]
          - option "T"
        - generic: ▾
      - button "Send" [disabled] [ref=e221]:
        - img [ref=e222]
        - text: Send
    - generic [ref=e225]:
      - generic [ref=e227]:
        - generic [ref=e228]:
          - button "Params" [ref=e229] [cursor=pointer]
          - button "Headers" [ref=e230] [cursor=pointer]
          - button "Body" [ref=e231] [cursor=pointer]
          - button "Auth" [ref=e232] [cursor=pointer]
          - button "Certs" [ref=e233] [cursor=pointer]
          - button "Tests" [ref=e234] [cursor=pointer]
          - button "Scripts" [ref=e235] [cursor=pointer]
          - button "Retry" [ref=e236] [cursor=pointer]
          - button "Notes" [ref=e237] [cursor=pointer]
        - generic [ref=e239]:
          - paragraph [ref=e240]: Query parameters
          - table [ref=e242]:
            - rowgroup [ref=e243]:
              - row "Name Value" [ref=e244]:
                - columnheader "Name" [ref=e245]
                - columnheader "Value" [ref=e246]
                - columnheader [ref=e247]
            - rowgroup [ref=e248]:
              - row "No query parameters" [ref=e249]:
                - cell "No query parameters" [ref=e250]
          - button "+ Add parameter" [ref=e251] [cursor=pointer]
      - generic [ref=e256]:
        - img [ref=e258]
        - paragraph [ref=e261]: No response yet
        - paragraph [ref=e262]: Hit Send or press ⌘⏎
  - contentinfo [ref=e264]:
    - button "sidecar v0.0.1 · 7m · 0m" [ref=e266] [cursor=pointer]:
      - generic [ref=e270]: sidecar v0.0.1
      - generic [ref=e271]: · 7m
      - generic [ref=e272]: · 0m
    - button "No env" [ref=e273] [cursor=pointer]:
      - generic [ref=e274]: No env
    - generic [ref=e275]:
      - button "Network Console" [ref=e276] [cursor=pointer]:
        - img [ref=e277]
      - button "Settings" [ref=e279] [cursor=pointer]:
        - img [ref=e280]
      - generic [ref=e283]: v0.0.1
  - generic [ref=e285]:
    - generic [ref=e286]:
      - generic [ref=e288]:
        - img [ref=e289]
        - text: Settings
      - generic [ref=e292]:
        - button "General" [ref=e293] [cursor=pointer]:
          - img [ref=e294]
          - text: General
        - button "AI" [ref=e297] [cursor=pointer]:
          - img [ref=e298]
          - text: AI
        - button "Editor" [ref=e301] [cursor=pointer]:
          - img [ref=e302]
          - text: Editor
        - button "Proxy" [ref=e304] [cursor=pointer]:
          - img [ref=e305]
          - text: Proxy
        - button "Shortcuts" [ref=e311] [cursor=pointer]:
          - img [ref=e312]
          - text: Shortcuts
        - button "About" [active] [ref=e314] [cursor=pointer]:
          - img [ref=e315]
          - text: About
    - generic [ref=e317]:
      - generic [ref=e318]:
        - generic [ref=e319]: About
        - button [ref=e320] [cursor=pointer]:
          - img [ref=e321]
      - generic [ref=e325]:
        - generic [ref=e326]:
          - heading "Theridion" [level=2] [ref=e327]
          - paragraph [ref=e328]: Modern API testing platform
          - paragraph [ref=e329]: v0.0.1
        - generic [ref=e330]:
          - paragraph [ref=e331]: Bruno UI/file-based ops + SoapUI WS-* strength + Playwright-style test runner.
          - paragraph [ref=e332]: "Protocols: REST, GraphQL, WebSocket, SOAP, Kafka, gRPC"
          - paragraph [ref=e333]: "Stack: Tauri 2 + React 18 + Python FastAPI"
        - paragraph [ref=e335]:
          - text: Named after the
          - emphasis [ref=e336]: Theridion
          - text: genus of cobweb spiders — a metaphor for tangled API dependencies.
      - generic [ref=e337]:
        - button "Cancel" [ref=e338] [cursor=pointer]
        - button "Save" [ref=e339] [cursor=pointer]
```

# Test source

```ts
  1  | import { test, expect } from "@playwright/test";
  2  | 
  3  | test.describe("settings modal", () => {
  4  |   test.beforeEach(async ({ page }) => {
  5  |     await page.goto("/");
  6  |     await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });
  7  |   });
  8  | 
  9  |   test("opens settings via Cmd+,", async ({ page }) => {
  10 |     await page.keyboard.press("Meta+,");
  11 |     await expect(page.getByText("Settings", { exact: false }).first()).toBeVisible();
  12 |   });
  13 | 
  14 |   test("all tabs are visible in settings sidebar", async ({ page }) => {
  15 |     await page.keyboard.press("Meta+,");
  16 | 
  17 |     // Verify all 6 tabs exist
  18 |     await expect(page.getByRole("button", { name: "General", exact: true })).toBeVisible();
  19 |     await expect(page.getByRole("button", { name: "AI", exact: true })).toBeVisible();
  20 |     await expect(page.getByRole("button", { name: "Editor", exact: true })).toBeVisible();
  21 |     await expect(page.getByRole("button", { name: "Proxy", exact: true })).toBeVisible();
  22 |     await expect(page.getByRole("button", { name: "Shortcuts", exact: true })).toBeVisible();
  23 |     await expect(page.getByRole("button", { name: "About", exact: true })).toBeVisible();
  24 |   });
  25 | 
  26 |   test("general tab shows theme options", async ({ page }) => {
  27 |     await page.keyboard.press("Meta+,");
  28 | 
  29 |     // General tab should be active by default — theme section visible
  30 |     await expect(page.getByText("Theme", { exact: true })).toBeVisible();
  31 |   });
  32 | 
  33 |   test("switching to Editor tab shows font size setting", async ({ page }) => {
  34 |     await page.keyboard.press("Meta+,");
  35 |     await page.getByRole("button", { name: "Editor", exact: true }).click();
  36 | 
  37 |     await expect(page.getByText("Font Size")).toBeVisible();
  38 |     // Font size input should exist with default value
  39 |     const fontInput = page.locator("input[type='number']").first();
  40 |     await expect(fontInput).toBeVisible();
  41 |     await expect(fontInput).toHaveValue("12");
  42 |   });
  43 | 
  44 |   test("switching to AI tab shows provider selection", async ({ page }) => {
  45 |     await page.keyboard.press("Meta+,");
  46 |     await page.getByRole("button", { name: "AI", exact: true }).click();
  47 | 
  48 |     await expect(page.getByText("Provider")).toBeVisible();
  49 |     // Default provider is Ollama
  50 |     await expect(page.getByTestId("ai-provider-select")).toHaveValue("ollama");
  51 |   });
  52 | 
  53 |   test("switching to Proxy tab shows proxy configuration", async ({ page }) => {
  54 |     await page.keyboard.press("Meta+,");
  55 |     await page.getByRole("button", { name: "Proxy", exact: true }).click();
  56 | 
  57 |     await expect(page.getByText("HTTP Proxy")).toBeVisible();
  58 |     await expect(page.getByText("SSL / TLS")).toBeVisible();
  59 |     await expect(page.getByPlaceholder("http://proxy.corp:8080")).toBeVisible();
  60 |   });
  61 | 
  62 |   test("switching to Shortcuts tab lists key bindings", async ({ page }) => {
  63 |     await page.keyboard.press("Meta+,");
  64 |     await page.getByRole("button", { name: "Shortcuts", exact: true }).click();
  65 | 
  66 |     await expect(page.getByText("Send request")).toBeVisible();
  67 |     await expect(page.getByText("New tab")).toBeVisible();
  68 |     await expect(page.getByText("Command palette")).toBeVisible();
  69 |   });
  70 | 
  71 |   test("switching to About tab shows app info", async ({ page }) => {
  72 |     await page.keyboard.press("Meta+,");
  73 |     await page.getByRole("button", { name: "About", exact: true }).click();
  74 | 
  75 |     await expect(page.getByText("Theridion").first()).toBeVisible();
> 76 |     await expect(page.getByText("v0.0.1")).toBeVisible();
     |                                            ^ Error: expect(locator).toBeVisible() failed
  77 |     await expect(page.getByText("Modern API testing platform")).toBeVisible();
  78 |   });
  79 | 
  80 |   test("close settings with Cancel button", async ({ page }) => {
  81 |     await page.keyboard.press("Meta+,");
  82 |     await expect(page.getByText("Theme", { exact: true })).toBeVisible();
  83 | 
  84 |     await page.getByRole("button", { name: "Cancel" }).click();
  85 |     // Modal should disappear
  86 |     await expect(page.getByText("Theme", { exact: true })).toBeHidden();
  87 |   });
  88 | 
  89 |   test("editor font size can be changed", async ({ page }) => {
  90 |     await page.keyboard.press("Meta+,");
  91 |     await page.getByRole("button", { name: "Editor", exact: true }).click();
  92 | 
  93 |     const fontInput = page.locator("input[type='number']").first();
  94 |     await fontInput.fill("14");
  95 |     await expect(fontInput).toHaveValue("14");
  96 |   });
  97 | });
  98 | 
```