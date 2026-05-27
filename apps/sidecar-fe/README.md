# Theridion Sidecar

Python FastAPI service that the Tauri shell consumes over loopback.

## Run

```bash
uv sync
uv run python -m theridion_sidecar.main
```

Or with a fixed port for development:

```bash
THERIDION_PORT=8765 uv run python -m theridion_sidecar.main
```

The first line printed to stdout is `THERIDION_SIDECAR_READY port=<N>` — the
Tauri parent process reads it to learn which port to talk to.

## Endpoints

- `GET /api/health` — liveness probe.
- `POST /api/requests/execute` — execute an HTTP request and return the
  response. Currently handles REST; future executors (SOAP, gRPC, GraphQL)
  will live alongside under `/api/requests/*`.
- `GET /docs` — interactive Swagger UI (dev only — the production build
  may disable this).

## Tests

```bash
uv run pytest
```
