# Theridion — Modern API Testing Platform

A local-first, open-source desktop application for testing APIs across every protocol. Built for developers and QA engineers who want full control over their API workflows without cloud lock-in.

![Theridion Screenshot](docs/screenshot.png)

## Key Features

- **REST** — Full HTTP client with environment variables, auth helpers, and response assertions
- **SOAP / WSDL** — Inspect services, execute operations, WS-Security support
- **GraphQL** — Introspection, variables panel, and query editor
- **gRPC** — Server reflection and unary invocation
- **WebSocket** — Connect, send frames, inspect messages
- **Kafka** — Produce and consume messages
- **Load Testing** — Embedded load runner with percentile stats and comparison reports
- **AI Test Generation** — Generate test cases from your API specs via local LLMs (Ollama)
- **Code Generation** — Export requests as Python, JavaScript, Go, Java, C#, cURL, PHP, or Ruby
- **Collection Runner** — Execute entire collections with assertions and HTML trace reports
- **File-Based Projects** — Git-friendly storage, no cloud sync required

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/qa-wave/theridion.git
cd theridion/apps/desktop
pnpm install

# 2. Build the Python sidecar
pnpm sidecar:bundle

# 3. Launch the app
pnpm tauri dev
```

**Prerequisites:** Node.js 24+, pnpm 10+, Rust (stable), Python 3.13+, [uv](https://github.com/astral-sh/uv)

## Why Theridion?

| | Postman | SoapUI | Bruno | Theridion |
|---|---|---|---|---|
| **Local-first / git-friendly** | Cloud-first | File-based | File-based | File-based |
| **SOAP + WS-Security** | Limited | Full | None | Full |
| **Load testing** | Cloud only | Built-in | None | Built-in |
| **Security scanning** | None | Built-in | None | Built-in |
| **Modern UI** | Yes | Dated | Yes | Yes |
| **Open source** | No | Partial | Yes | Yes |
| **Test runner + trace report** | Basic | JUnit XML | None | Playwright-style |

Named after *Theridion*, a genus of spiders that build chaotic three-dimensional cobwebs — a fitting metaphor for the entangled dependencies of modern APIs.

## Tech Stack

| Layer | Technology |
|---|---|
| Desktop shell | Tauri 2 (Rust) |
| Frontend | React 18 + TypeScript + Tailwind CSS + Monaco Editor |
| Backend | Python FastAPI sidecar (bundled via PyInstaller) |
| HTTP engine | httpx with HTTP/2 |
| SOAP | zeep |
| Package management | pnpm (JS), uv (Python) |

## Development

```bash
# Run sidecar tests (< 1s)
cd apps/sidecar && uv run pytest -q

# Run E2E tests (~9s)
cd apps/desktop && pnpm test:e2e

# TypeScript type check
cd apps/desktop && pnpm typecheck

# Standalone sidecar for fast Python iteration
cd apps/sidecar && THERIDION_PORT=8765 uv run python -m theridion_sidecar.main
```

See [CLAUDE.md](./CLAUDE.md) for full architecture docs, conventions, and roadmap.

## License

MIT — see [LICENSE](./LICENSE).
