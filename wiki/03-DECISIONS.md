# Theridion FE — ADR index

## ADR-001 — Multi-framework adapter, ne Playwright-only
**Stav:** Accepted
**Kontext:** Týmy s existujícími Cypress / Selenium / WebdriverIO suites nemají rozpočet na rewrite. Playwright-only by je vyřadil.
**Rozhodnutí:** Theridion DSL + adapter per framework (Playwright primary, ostatní beta).
**Důsledky:**
- ✅ Adresuje větší trh než Playwright-only nástroje
- ❌ Adapter údržba — 5 backendů × každý feature
- ❌ DSL musí být schopen vyjádřit nejmenší společný jmenovatel + escape hatches pro pokročilé use case

## ADR-002 — Slim sidecar, žádný subprocess Python pluginů
**Stav:** Accepted (2026-05-28)
**Kontext:** FE sidecar potřebuje jen environment substituci + Silk orchestraci + history. Plný BE sidecar (46 MB) je 2× větší než nutné.
**Rozhodnutí:** Slim sidecar (apps/sidecar-fe) drops grpcio/zeep/kafka/jdbc/mqtt deps. Bundle target ~30 MB.
**Důsledky:**
- ✅ Faster cold start (~5 s vs 8 s)
- ✅ Menší distribuovaná binárka
- ❌ Duplikovaný sidecar code — sdílený `packages/sidecar-core` až post-V1

## ADR-003 — Playwright Codegen jako recorder backend
**Stav:** Accepted
**Kontext:** Vlastní recorder engine = browser extension + Chrome DevTools Protocol integrace = velký scope.
**Rozhodnutí:** Wrapped Playwright Codegen (`npx playwright codegen`), capture stdout/stderr, převod na Theridion DSL.
**Důsledky:**
- ✅ Robust selector heuristics (role / label / text / css fallback)
- ✅ Žádný custom engine
- ❌ Recorder out je Playwright-flavored; export do Cypress/Selenium přes adapter převod

## ADR-004 — `npx` lazy resolution místo bundle
**Stav:** Accepted
**Kontext:** Playwright bundling = +200 MB, browsers další ~500 MB. Nelze rozumně shipovat ve V1.
**Rozhodnutí:** Sidecar volá `npx playwright …` jako subprocess. Browsers se instalují on-demand přes Settings dialog.
**Důsledky:**
- ✅ Theridion FE bundle zůstává ~30 MB
- ✅ Users mohou používat globálně nainstalovaný Playwright / Cypress
- ❌ First run UX — uživatel musí mít node nainstalovaný + browsers download

## ADR-005 — Distinct violet branding
**Stav:** Accepted (2026-05-29)
**Kontext:** Theridion BE + FE side-by-side v Launchpadu potřebují vizuálně odlišit. Stejné spider logo + jiná barva.
**Rozhodnutí:** FE má violet accent (#8b5cf6), BE emerald. Icons regenerovány přes ImageMagick hue-shift +60°.
**Důsledky:**
- ✅ V Launchpad / Start menu jasně rozlišitelné
- ✅ Brand soudržnost (stejný spider, jen barva)
