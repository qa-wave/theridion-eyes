# Theridion FE — architektura

```
┌────────────────────────────────────────────────────────────────┐
│  Tauri 2.11 shell (Rust, ~5 MB) — com.theridion.fe             │
│  ├── src-tauri/src/lib.rs                                      │
│  └── WebView                                                   │
│       │                                                        │
│       ▼ React 18 + TypeScript + Tailwind                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ App.tsx → ActivityBar (silk/monitors/hubOverview)        │  │
│  │ → SilkPanel (recorder + run history + trace viewer)      │  │
│  └─────────────────────────┬────────────────────────────────┘  │
└────────────────────────────┼───────────────────────────────────┘
                             │ loopback HTTP, X-Theridion-Token
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Python sidecar — apps/sidecar-fe (PyInstaller, ~30 MB target) │
│  ├── theridion_sidecar/main.py     (slim, 5 routerů)           │
│  ├── api/silk.py    Playwright orchestration via npx           │
│  ├── api/health.py + api/diagnostics.py                        │
│  ├── api/environments.py    env vars + substituce              │
│  └── api/history.py    persisted run history                   │
└────────────────────────────┬───────────────────────────────────┘
                             │ subprocess (npx)
                             ▼
                  ┌──────────────────────────────┐
                  │ Playwright / Cypress / WDIO  │
                  │ Selenium / Puppeteer         │
                  │ (lazy resolved via npx)      │
                  └──────────────────────────────┘
```

## Co je jinak vs Theridion BE

| | BE | FE |
|---|---|---|
| Identifier | com.theridion.be | com.theridion.fe |
| Dev port | 1420 | 1430 |
| Sidecar deps | grpcio + zeep + kafka + jdbc + mqtt + stomp (full) | slim — fastapi + httpx + pydantic + lxml + jsonpath |
| Bundle size | ~46 MB | ~30 MB target |
| Sidecar pid file | sidecar.pid | sidecar-fe.pid (co-run safe) |
| Sidecar token file | sidecar-token | sidecar-fe-token |
| Accent | emerald | violet |
| Routes | ~150 routerů | 5 routerů (silk, health, diagnostics, environments, history) |
| Main panels | Strand, Mesh, Surge, Snare | Silk, Monitors, HubOverview |

## Multi-framework adapter

Theridion runner adapter převádí `spec.thr` (TypeScript-flavored DSL) na backend-specific kód:

```
spec.thr (Theridion DSL)
  ├── Playwright adapter   → exports .ts s `@playwright/test`
  ├── Cypress adapter      → exports .js s `cy.*`
  ├── WebdriverIO adapter  → exports .ts s `browser.$` API
  ├── Selenium adapter     → exports .py s `selenium.webdriver`
  └── Puppeteer adapter    → exports .ts s `puppeteer.launch`
```

Cross-framework export = jedna z killer features. Spec napsaný jednou, runtime
volený per-run nebo per-target browser matrix.

## File storage layout

```
~/.theridion/
├── silk/
│   ├── specs/<name>.thr           native Theridion DSL
│   ├── runs/<timestamp>.json      run results
│   ├── baselines/<spec>/<browser>.png   visual baselines
│   └── recordings/<timestamp>.json      Codegen sessions
├── environments/
├── sidecar-fe-token               chmod 600
├── sidecar-fe.pid
└── settings.json
```
