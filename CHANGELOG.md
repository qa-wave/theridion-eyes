# Changelog

## [Unreleased]

### Added
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
