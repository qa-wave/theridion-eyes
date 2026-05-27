"""Theridion FE sidecar entrypoint.

Slim FastAPI sidecar — only routers needed for Playwright (Silk) frontend
testing. Keeps the same dynamic-port handshake, auth-token middleware, CORS
regex and lifespan management as the BE sidecar so the Tauri shell code can
stay identical.

Routers registered:
  - health         (always — Tauri liveness probe)
  - diagnostics    (always — Tauri "Open diagnostics" UI)
  - environments   (Silk runs need env vars)
  - history        (run history list)
  - silk           (Playwright codegen + runner)
"""

from __future__ import annotations

import atexit
import logging
import os
import secrets
import socket
import stat
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

from theridion_sidecar import __version__, storage
from theridion_sidecar.api.diagnostics import router as diagnostics_router
from theridion_sidecar.api.environments import router as environments_router
from theridion_sidecar.api.health import router as health_router
from theridion_sidecar.api.history import router as history_router
from theridion_sidecar.api.silk import router as silk_router


_EXEMPT_PATHS = {"/api/health", "/api/diagnostics", "/api/readiness"}

# Module-level token — generated once at import time so monkeypatched tests
# can override via THERIDION_TOKEN or setattr before first use.
_SIDECAR_TOKEN: str = os.environ.get("THERIDION_TOKEN") or secrets.token_urlsafe(32)


def get_sidecar_token() -> str:
    return _SIDECAR_TOKEN


class _TokenAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests without X-Theridion-Token header (except health probes)."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)
        provided = request.headers.get("X-Theridion-Token", "")
        if provided != _SIDECAR_TOKEN:
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid or missing X-Theridion-Token"},
            )
        return await call_next(request)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Shared httpx pool — Silk fetches mock pages, scheduled run uploads."""
    limits = httpx.Limits(
        max_connections=50,
        max_keepalive_connections=10,
        keepalive_expiry=30.0,
    )
    transport = httpx.AsyncHTTPTransport(http2=True, limits=limits)
    app.state.http_client = httpx.AsyncClient(
        transport=transport,
        timeout=30.0,
        follow_redirects=True,
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()


def _token_file_path() -> Path:
    """~/.theridion/sidecar-fe-token (distinct from BE token to allow co-run)."""
    return Path.home() / ".theridion" / "sidecar-fe-token"


def _write_token_file(token: str) -> None:
    try:
        token_path = _token_file_path()
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(token, encoding="utf-8")
        token_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except OSError as exc:
        print(f"warning: could not write token file: {exc}", file=sys.stderr)


def create_app() -> FastAPI:
    _debug = bool(os.getenv("THERIDION_DEBUG"))
    app = FastAPI(
        title="Theridion FE sidecar",
        version=__version__,
        docs_url="/docs" if _debug else None,
        redoc_url="/redoc" if _debug else None,
        openapi_url="/openapi.json" if _debug else None,
        lifespan=_lifespan,
    )

    @app.exception_handler(Exception)
    async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled exception on %s %s: %s",
            request.method,
            request.url.path,
            traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "internal server error"},
        )

    @app.get("/api/readiness", tags=["health"])
    async def readiness() -> dict:
        home = storage.home_dir()
        if not home.exists():
            return JSONResponse(  # type: ignore[return-value]
                status_code=503,
                content={"status": "unavailable", "reason": "storage dir missing"},
            )
        return {"status": "ok", "storage": str(home), "product": "fe"}

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=(
            r"^(?:https?://(?:localhost|127\.0\.0\.1)(?::\d+)?"
            r"|tauri://localhost"
            r"|https://tauri\.localhost)$"
        ),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(_TokenAuthMiddleware)

    # Slim router set — only what Silk + base Tauri shell need
    app.include_router(health_router)
    app.include_router(diagnostics_router)
    app.include_router(environments_router)
    app.include_router(history_router)
    app.include_router(silk_router)

    return app


app = create_app()


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _write_pid_file(port: int) -> None:
    pid_path = storage.home_dir() / "sidecar-fe.pid"
    try:
        storage.home_dir().mkdir(parents=True, exist_ok=True)
        pid_path.write_text(f"{os.getpid()}:{port}\n", encoding="utf-8")
    except OSError as e:
        print(f"warning: could not write {pid_path}: {e}", file=sys.stderr)
        return

    def _cleanup() -> None:
        try:
            current = pid_path.read_text(encoding="utf-8").strip()
            if current.startswith(f"{os.getpid()}:"):
                pid_path.unlink(missing_ok=True)
        except OSError:
            pass

    atexit.register(_cleanup)


def main() -> None:
    port_env = os.environ.get("THERIDION_PORT")
    port = int(port_env) if port_env else _pick_free_port()
    _write_pid_file(port)
    _write_token_file(_SIDECAR_TOKEN)

    print(
        f"THERIDION_SIDECAR_READY pid={os.getpid()} port={port} "
        f"home={storage.home_dir()} product=fe",
        flush=True,
    )
    uvicorn.run(
        "theridion_sidecar.main:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
        timeout_graceful_shutdown=30,
    )


if __name__ == "__main__":
    sys.exit(main())
