# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: graphql.spec.ts >> GraphQL modal >> closes modal with X button
- Location: tests/e2e/graphql.spec.ts:89:3

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for locator('button').filter({ has: locator('svg.lucide-x') }).first()
    - locator resolved to <button type="button" class="group relative flex items-center gap-2 rounded-md py-1.5 text-xs transition-all duration-150  max-w-[240px] px-3 bg-neutral-800/70 text-neutral-100 shadow-inner-glow">…</button>
  - attempting click action
    2 × waiting for element to be visible, enabled and stable
      - element is visible, enabled and stable
      - scrolling into view if needed
      - done scrolling
      - <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">…</div> intercepts pointer events
    - retrying click action
    - waiting 20ms
    2 × waiting for element to be visible, enabled and stable
      - element is visible, enabled and stable
      - scrolling into view if needed
      - done scrolling
      - <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">…</div> intercepts pointer events
    - retrying click action
      - waiting 100ms
    44 × waiting for element to be visible, enabled and stable
       - element is visible, enabled and stable
       - scrolling into view if needed
       - done scrolling
       - <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">…</div> intercepts pointer events
     - retrying click action
       - waiting 500ms
    - waiting for element to be visible, enabled and stable

```

# Page snapshot

```yaml
- generic [ref=e1]:
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
      - button "sidecar v0.0.1 · 1m · 0m" [ref=e251] [cursor=pointer]:
        - generic [ref=e255]: sidecar v0.0.1
        - generic [ref=e256]: · 1m
        - generic [ref=e257]: · 0m
      - button "No env" [ref=e258] [cursor=pointer]:
        - generic [ref=e259]: No env
      - generic [ref=e260]:
        - button "Network Console" [ref=e261] [cursor=pointer]:
          - img [ref=e262]
        - button "Settings" [ref=e264] [cursor=pointer]:
          - img [ref=e265]
        - generic [ref=e268]: v0.0.1
    - generic [ref=e270]:
      - generic [ref=e271]:
        - generic [ref=e272]:
          - img [ref=e273]
          - text: GraphQL
        - button [active] [ref=e276] [cursor=pointer]:
          - img [ref=e277]
      - generic [ref=e280]:
        - generic [ref=e281]: GQL
        - textbox "https://api.example.com/graphql" [ref=e282]
        - button "Schema" [disabled] [ref=e283]:
          - img [ref=e284]
          - text: Schema
        - button "Run" [disabled] [ref=e287]:
          - img [ref=e288]
          - text: Run
      - generic [ref=e290]:
        - generic [ref=e291]:
          - generic [ref=e292]: Query
          - code [ref=e297]:
            - generic [ref=e298]:
              - textbox "Editor content" [ref=e299]
              - textbox [ref=e300]
              - generic [ref=e302]:
                - generic [ref=e303]:
                  - generic [ref=e305] [cursor=pointer]: 
                  - generic [ref=e306]: "1"
                - generic [ref=e308]: "2"
                - generic [ref=e310]: "3"
              - generic [ref=e316]:
                - generic [ref=e318]: "query {"
                - generic [ref=e320]: __typename
                - generic [ref=e322]: "}"
          - generic [ref=e324]: Variables
          - code [ref=e329]:
            - generic [ref=e330]:
              - textbox "Editor content" [ref=e331]
              - textbox [ref=e332]
              - generic [ref=e337]: "1"
              - generic [ref=e343]: "{}"
          - generic [ref=e345]: Headers
          - code [ref=e350]:
            - generic [ref=e351]:
              - textbox "Editor content" [ref=e352]
              - textbox [ref=e353]
              - generic [ref=e358]: "1"
              - generic [ref=e364]: "{}"
        - generic [ref=e366]:
          - generic [ref=e367]:
            - button "Response" [ref=e368] [cursor=pointer]: Response
            - button "Schema" [ref=e370] [cursor=pointer]
          - generic [ref=e372]:
            - img [ref=e373]
            - text: Run a query to see results
  - generic [ref=e376]:
    - alert
    - alert
```

# Test source

```ts
  1   | import { test, expect } from "@playwright/test";
  2   | 
  3   | test.describe("GraphQL modal", () => {
  4   |   test.beforeEach(async ({ page }) => {
  5   |     await page.goto("/");
  6   |     await expect(page.getByText(/sidecar v\d/)).toBeVisible({ timeout: 10_000 });
  7   |   });
  8   | 
  9   |   test("opens GraphQL modal via command palette", async ({ page }) => {
  10  |     // Open command palette with Cmd+K
  11  |     await page.keyboard.press("Meta+k");
  12  |     await expect(page.getByPlaceholder(/Type a command/i)).toBeVisible();
  13  | 
  14  |     // Type "GraphQL" and select the action
  15  |     await page.getByPlaceholder(/Type a command/i).fill("Open GraphQL");
  16  |     await page.getByText("Open GraphQL", { exact: false }).first().click();
  17  | 
  18  |     // Modal should be open with the GQL badge and URL input
  19  |     await expect(page.getByText("GraphQL", { exact: true })).toBeVisible();
  20  |     await expect(
  21  |       page.getByPlaceholder("https://api.example.com/graphql"),
  22  |     ).toBeVisible();
  23  |   });
  24  | 
  25  |   test("has query editor with default content", async ({ page }) => {
  26  |     await page.keyboard.press("Meta+k");
  27  |     await page.getByPlaceholder(/Type a command/i).fill("Open GraphQL");
  28  |     await page.getByText("Open GraphQL", { exact: false }).first().click();
  29  | 
  30  |     // The modal should show the Query section label
  31  |     await expect(page.getByText("Query", { exact: true })).toBeVisible();
  32  |     // Variables and Headers sections should also be present
  33  |     await expect(page.getByText("Variables", { exact: true })).toBeVisible();
  34  |     await expect(page.getByText("Headers", { exact: true })).toBeVisible();
  35  |   });
  36  | 
  37  |   test("schema introspection button exists and is initially disabled", async ({
  38  |     page,
  39  |   }) => {
  40  |     await page.keyboard.press("Meta+k");
  41  |     await page.getByPlaceholder(/Type a command/i).fill("Open GraphQL");
  42  |     await page.getByText("Open GraphQL", { exact: false }).first().click();
  43  | 
  44  |     // Schema button should exist but be disabled when URL is empty
  45  |     const schemaBtn = page.getByRole("button", { name: "Schema" });
  46  |     await expect(schemaBtn).toBeVisible();
  47  |     await expect(schemaBtn).toBeDisabled();
  48  | 
  49  |     // Enter a URL — schema button should become enabled
  50  |     await page
  51  |       .getByPlaceholder("https://api.example.com/graphql")
  52  |       .fill("http://localhost:1234/graphql");
  53  |     await expect(schemaBtn).toBeEnabled();
  54  |   });
  55  | 
  56  |   test("run button is disabled without URL and query", async ({ page }) => {
  57  |     await page.keyboard.press("Meta+k");
  58  |     await page.getByPlaceholder(/Type a command/i).fill("Open GraphQL");
  59  |     await page.getByText("Open GraphQL", { exact: false }).first().click();
  60  | 
  61  |     const runBtn = page.getByRole("button", { name: "Run" });
  62  |     await expect(runBtn).toBeDisabled();
  63  | 
  64  |     // Fill URL only — still disabled if query is somehow empty? No, default
  65  |     // query exists ("query { __typename }"), so once URL is filled it enables.
  66  |     await page
  67  |       .getByPlaceholder("https://api.example.com/graphql")
  68  |       .fill("http://localhost:1234/graphql");
  69  |     await expect(runBtn).toBeEnabled();
  70  |   });
  71  | 
  72  |   test("response tab shows placeholder when no query has been run", async ({
  73  |     page,
  74  |   }) => {
  75  |     await page.keyboard.press("Meta+k");
  76  |     await page.getByPlaceholder(/Type a command/i).fill("Open GraphQL");
  77  |     await page.getByText("Open GraphQL", { exact: false }).first().click();
  78  | 
  79  |     // Response and Schema tabs should exist
  80  |     await expect(page.getByRole("button", { name: "Response" })).toBeVisible();
  81  |     await expect(
  82  |       page.getByRole("button", { name: "Schema" }).nth(0),
  83  |     ).toBeVisible();
  84  | 
  85  |     // Placeholder text in response area
  86  |     await expect(page.getByText("Run a query to see results")).toBeVisible();
  87  |   });
  88  | 
  89  |   test("closes modal with X button", async ({ page }) => {
  90  |     await page.keyboard.press("Meta+k");
  91  |     await page.getByPlaceholder(/Type a command/i).fill("Open GraphQL");
  92  |     await page.getByText("Open GraphQL", { exact: false }).first().click();
  93  | 
  94  |     await expect(page.getByText("GraphQL", { exact: true })).toBeVisible();
  95  | 
  96  |     // Close via X button (the close button in the header)
  97  |     await page
  98  |       .locator("button")
  99  |       .filter({ has: page.locator("svg.lucide-x") })
  100 |       .first()
> 101 |       .click();
      |        ^ Error: locator.click: Test timeout of 30000ms exceeded.
  102 | 
  103 |     // Modal should disappear
  104 |     await expect(
  105 |       page.getByPlaceholder("https://api.example.com/graphql"),
  106 |     ).toBeHidden();
  107 |   });
  108 | });
  109 | 
```