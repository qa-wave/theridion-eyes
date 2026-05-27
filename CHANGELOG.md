# Changelog

## [Unreleased]

### Added — desktop product split

- **Theridion BE** (`apps/studio`) — rebranded from "Theridion Studio".
  Identifier `com.theridion.be`. Full backend & integration testing surface:
  REST, GraphQL, gRPC, SOAP/WS-Security, Kafka, JMS, JDBC, MQTT.
- **Theridion FE** (`apps/studio-fe`, NEW) — separate Tauri desktop product
  for Playwright frontend automation. Identifier `com.theridion.fe`.
  Distinct dev port (1430), distinct pid+token files so both apps can run
  side-by-side. ActivityBar reduced to 3 modes (silk / monitors / hubOverview)
  with violet accent.
- **Theridion FE sidecar** (`apps/sidecar-fe`, NEW) — slimmed Python sidecar.
  Drops grpcio + zeep/xmlsec + aiokafka + paho-mqtt + psycopg2 + stomp-py
  (~20 MB savings). Bundle target ~30 MB. Only registers health, diagnostics,
  environments, history, silk routers.
- **Desktop release pipeline** (`.github/workflows/desktop-release.yml`) —
  tag-triggered (v*.*.*) gate → draft release → 4 OS × 2 apps = 8 build
  jobs. Bundle formats per OS: macOS dmg+app, Linux deb+AppImage,
  Windows msi+nsis. Code signing + notarization hooks ready (secrets-gated).
- **Tauri auto-updater** — both products read `latest-be.json` / `latest-fe.json`
  from GitHub Releases.

### Added — Hub web platform

- **Theridion Hub** (`apps/hub`) — Next.js team dashboard rebranded from
  internal "Zorník" name across BrandingForm fallback, ServiceMap label,
  OnboardingWizard copy, DB defaults, and i18n cookie keys.
- **Migration shim** (`src/lib/branding/store.ts`) — `migrateLegacyBrand()`
  rewrites persisted Blob branding from "Zorník"/"Zornik" → "Theridion Hub"
  on first read, then persists back. Idempotent, one-shot.
- **/tests/be** + **/tests/fe** subapps with full route segments:
  - BE: protocol grid (8 protocols GA/Beta), KPI cards, per-env BE run
    matrix scoped to backend/api/worker apps + Studio download CTA.
  - FE: browser coverage matrix (Chromium/Firefox/WebKit), capability
    tiles (Codegen / visual / a11y / network), FE run matrix, Runner CLI
    snippet.
- **RBAC permissions** — extended `Permission` union with `tests:be:view`,
  `tests:be:trigger`, `tests:fe:view`, `tests:fe:trigger`, `runs:view`,
  `runs:trigger`, `runs:delete`. New `qa-engineer` system role (BE+FE
  trigger). PermissionsProvider + Gate primitives for declarative UI gating.
- **Security baseline** — distributed via `bin/sync-security.py`
  internal-only profile: arcjet (DRY_RUN), sentry-tags helper, x-honeypot
  endpoint (410 Gone + telemetry), robots.txt + ai.txt + llms.txt with
  AI-crawler block list. proxy.ts upgraded with COOP/CORP/Permissions-Policy
  + X-Robots-Tag (noai for public, noai+noindex for dashboard/api).

### Added — pre-split features
- REST, GraphQL, WebSocket, SOAP/WSDL, Kafka, gRPC protocol support
- MCP Server v2 (10 tools, Claude Desktop integration)
- Self-healing assertions with Levenshtein fuzzy matching
- AI test generation via Ollama (privacy-first)
- Agentic API Explorer (autonomous endpoint discovery)
- Playwright-style HTML Trace Viewer
- Contract Guard (OpenAPI auto-validation)
- Variable Inspector (live scope debugger)
- Network Console (Chrome DevTools style)
- 10 visual themes (4 color + 6 style)
- Universal import (Postman, Insomnia, HAR, Hoppscotch, Thunder Client, OpenAPI, SoapUI, Bruno, HTTPie, cURL)
- Command palette (Cmd+K) with fuzzy search and grouped sections
- Collection runner with CLI (`theridion test`) and HTML trace reports
- Toast notification system with micro-interactions
- Drag-drop reorder, pin tabs, auto-save drafts
- Environment color coding and keyboard switching (Ctrl+E)

### Security
- Fernet encryption (replaced XOR)
- Auth token middleware for sidecar API
- Removed terminal.py and npm_loader.py (RCE vulnerabilities)
