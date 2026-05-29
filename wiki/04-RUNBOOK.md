# Theridion FE — runbook

## First-time setup

```bash
git clone git@github.com:qa-wave/theridion-fe.git
cd theridion-fe/apps/studio-fe
pnpm install
pnpm sidecar:bundle          # builds slim ~30 MB PyInstaller bundle
pnpm tauri:dev               # opens window (port 1430)
```

Před prvním Silk runem aplikace zeptá user na instalaci Playwright browsers
(`npx playwright install`). To je on-demand download ~500 MB cache.

## Test stack

```bash
# Sidecar pytest (~65 tests, < 2s)
cd apps/sidecar-fe && uv run pytest -q

# Frontend typecheck
cd apps/studio-fe && pnpm typecheck

# Rust unit
cd apps/studio-fe/src-tauri && cargo test --lib
```

## Release `v0.x.y`

Stejný flow jako BE:

1. Update CHANGELOG.md
2. `git tag vX.Y.Z && git push origin vX.Y.Z`
3. CI builds 4 OS targets → draft release
4. Verify + promote

## Troubleshooting

### "browsers not installed" při Silk runu

V Theridion FE UI: Settings → Tool integrations → Install Playwright browsers.
Nebo manually: `npx playwright install chromium firefox webkit`.

### Sidecar nestartuje (BE pid file conflict)

BE i FE mohou běžet současně, ale pokud BE crash zanechal stale `~/.theridion/sidecar.pid`,
FE může mylně myslet, že běží. Smaž `~/.theridion/sidecar-fe.pid` a restartuj.

### Cross-framework export nefunguje

Adapter status:
- Playwright: GA — `theridion-runner export-playwright` plně funkční
- Cypress: Beta — některé features (intercept) nemapované
- WebdriverIO: Beta — async chain mapping není 100% kompletní
- Selenium: Beta — fluent waits/expect API rozdílné
- Puppeteer: Alpha — recorder export only, manual cleanup nutný

### Updater "incorrect updater private key password"

Stejný issue jako BE — `TAURI_SIGNING_PRIVATE_KEY` musí být raw content `.key`:

```bash
cat ~/.tauri/theridion-fe.update.key | gh secret set TAURI_SIGNING_PRIVATE_KEY --repo qa-wave/theridion-fe
```

## Příbuzné runbooks

- [theridion-be runbook](../../theridion-be/wiki/04-RUNBOOK.md)
- [theridion-hub runbook](../../theridion-hub/wiki/04-RUNBOOK.md)
