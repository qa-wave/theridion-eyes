# Theridion FE — doména

## Co řešíme

FE QA inženýr potřebuje jeden nástroj, ve kterém umí nahrávat scénáře přes recorder,
spustit je v Playwright / Cypress / Selenium / WebdriverIO / Puppeteer (bez nutnosti
přepsat test) a publikovat výsledky do týmového dashboardu.

## Proč ne Playwright samotný

Playwright je výborný, ale uzamyká tě v jeho ekosystému. Spousty teams má existující
Cypress / Selenium / WebdriverIO suites a nechce je přepisovat. Theridion FE adapter
normalizuje assertion DSL napříč backendy — uživatel napíše scénář jednou, vybere
runtime na úrovni run config.

## Cílový uživatel

- **FE QA inženýr** — recorder + replay + batch run
- **Vývojář** — quick E2E smoke v devel iteraci
- **Test automation engineer** — multi-framework support, framework migration (např. Selenium → Playwright)

## Co NEdělá

- Backend API testing (Theridion BE)
- Quality gates monitoring (Theridion Hub)
- Mobile native automation (Appium) — odloženo
- Visual baseline cloud review — V1 jen local baseline

## Hlavní entity

- **Spec** — test scénář v Theridion DSL (TypeScript-flavored), exportovatelný do Playwright/Cypress/Selenium
- **Run** — výsledek spuštění specu na konkrétním frameworku × browseru, persistovaný v `~/.theridion/silk/runs/`
- **Baseline** — visual regression snapshot (PNG per browser × viewport)
- **RecorderSession** — Playwright Codegen wrapped, click-to-pick locator, action replay

## Multi-framework matrix

| Spec authoring | Playwright | Cypress | WebdriverIO | Selenium | Puppeteer |
|---|---|---|---|---|---|
| Native run | ✓ GA | Beta | Beta | Beta | Alpha |
| Recorder export | ✓ | ✓ | ✓ | ✓ | ✓ |
| Multi-browser | Chromium/FF/WK | Chromium | Selenium browsers | Chrome/FF/Edge/Safari | Chromium |
| Visual diff | ✓ | ✓ | ✓ | ✓ (separate) | ✓ |
| a11y (axe-core) | ✓ injected | ✓ | ✓ | ✓ | ✓ |
| Network intercept | ✓ | ✓ (cy.intercept) | ✓ | Limited | ✓ |
