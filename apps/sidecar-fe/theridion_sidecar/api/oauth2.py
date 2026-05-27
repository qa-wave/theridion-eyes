"""OAuth2 flows: authorization_code+PKCE, client_credentials, password (deprecated).

Endpoints
---------
POST /api/auth/oauth2/authorize-url          Build authorization URL (PKCE optional)
POST /api/auth/oauth2/callback-server/start  Start loopback callback server
GET  /api/auth/oauth2/callback-server/result Poll callback result
POST /api/auth/oauth2/callback-server/stop   Stop callback server
POST /api/auth/oauth2/token                  Exchange auth code for tokens
POST /api/auth/oauth2/refresh                Refresh access token (with rotation)
POST /api/auth/oauth2/client-credentials     Client Credentials grant (server-to-server)
POST /api/auth/oauth2/token-reuse            Check / auto-refresh cached token in env vars
POST /api/auth/oauth2/password               Resource Owner Password grant (DEPRECATED)
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------


def generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier = secrets.token_urlsafe(96)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class OAuth2TokenRequest(BaseModel):
    """Parameters for the OAuth2 authorization_code token exchange."""

    token_url: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: str = ""
    code: str = Field(..., min_length=1)
    redirect_uri: str = ""
    scope: str = ""
    grant_type: str = "authorization_code"
    code_verifier: str = ""


class OAuth2TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None
    raw: dict[str, object] = Field(default_factory=dict)


class AuthorizeUrlInput(BaseModel):
    auth_url: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    redirect_uri: str = "http://localhost:9876/oauth2/callback"
    scope: str = ""
    state: str | None = None
    use_pkce: bool = True


class AuthorizeUrlOutput(BaseModel):
    url: str
    state: str
    code_verifier: str | None = None
    code_challenge: str | None = None


class CallbackServerStartInput(BaseModel):
    port: int = 9876
    timeout_seconds: int = 300


class CallbackServerStartOutput(BaseModel):
    port: int
    status: str


class CallbackServerResult(BaseModel):
    status: str  # "waiting", "received", "expired", "not_running"
    code: str | None = None
    state: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# In-process callback server state
# ---------------------------------------------------------------------------


class _CallbackState:
    """Mutable state shared between the HTTP callback handler and the
    FastAPI endpoints. Only one callback server can run at a time."""

    lock = threading.Lock()
    server: HTTPServer | None = None
    thread: threading.Thread | None = None
    code: str | None = None
    state: str | None = None
    error: str | None = None
    received: bool = False


_cb = _CallbackState()


class _CallbackHandler(BaseHTTPRequestHandler):
    """Tiny HTTP handler that captures the OAuth2 redirect."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.rstrip("/").endswith("/oauth2/callback"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        qs = parse_qs(parsed.query)
        with _cb.lock:
            _cb.code = qs.get("code", [None])[0]  # type: ignore[assignment]
            _cb.state = qs.get("state", [None])[0]  # type: ignore[assignment]
            _cb.error = qs.get("error", [None])[0]  # type: ignore[assignment]
            _cb.received = True

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = (
            "<!DOCTYPE html><html><body>"
            "<h2>Authorization successful!</h2>"
            "<p>You can close this tab and return to Theridion.</p>"
            "</body></html>"
        )
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stderr logging."""


def _run_server(port: int, timeout: int) -> None:
    """Run the callback HTTP server in a background thread."""
    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    server.timeout = 1.0  # poll interval for checking the stop flag
    with _cb.lock:
        _cb.server = server
        _cb.code = None
        _cb.state = None
        _cb.error = None
        _cb.received = False

    elapsed = 0.0
    try:
        while elapsed < timeout:
            server.handle_request()
            with _cb.lock:
                if _cb.received:
                    break
            elapsed += 1.0
    finally:
        server.server_close()
        with _cb.lock:
            _cb.server = None
            _cb.thread = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/oauth2/authorize-url", response_model=AuthorizeUrlOutput)
async def build_authorize_url(req: AuthorizeUrlInput) -> AuthorizeUrlOutput:
    """Generate an OAuth2 authorization URL, optionally with PKCE S256."""
    state = req.state or secrets.token_urlsafe(32)
    code_verifier: str | None = None
    code_challenge: str | None = None

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": req.client_id,
        "redirect_uri": req.redirect_uri,
        "state": state,
    }
    if req.scope:
        params["scope"] = req.scope

    if req.use_pkce:
        code_verifier, code_challenge = generate_pkce()
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    # Build URL preserving any existing query params
    parsed = urlparse(req.auth_url)
    existing_qs = parse_qs(parsed.query, keep_blank_values=True)
    for k, v in existing_qs.items():
        if k not in params:
            params[k] = v[0]
    url = parsed._replace(query=urlencode(params)).geturl()

    return AuthorizeUrlOutput(
        url=url,
        state=state,
        code_verifier=code_verifier,
        code_challenge=code_challenge,
    )


@router.post(
    "/oauth2/callback-server/start",
    response_model=CallbackServerStartOutput,
)
async def start_callback_server(
    body: CallbackServerStartInput,
) -> CallbackServerStartOutput:
    """Start a temporary HTTP server that waits for the OAuth2 callback."""
    with _cb.lock:
        if _cb.thread is not None and _cb.thread.is_alive():
            raise HTTPException(
                status_code=409,
                detail="callback server already running",
            )

    thread = threading.Thread(
        target=_run_server,
        args=(body.port, body.timeout_seconds),
        daemon=True,
    )
    with _cb.lock:
        _cb.thread = thread
    thread.start()

    # Give the server a moment to bind
    await asyncio.sleep(0.1)

    return CallbackServerStartOutput(port=body.port, status="listening")


@router.get(
    "/oauth2/callback-server/result",
    response_model=CallbackServerResult,
)
async def get_callback_result() -> CallbackServerResult:
    """Poll for the captured authorization code."""
    with _cb.lock:
        if _cb.received:
            return CallbackServerResult(
                status="received",
                code=_cb.code,
                state=_cb.state,
                error=_cb.error,
            )
        if _cb.thread is not None and _cb.thread.is_alive():
            return CallbackServerResult(status="waiting")
        if _cb.thread is not None:
            # Thread finished without receiving — timeout
            return CallbackServerResult(status="expired")
    return CallbackServerResult(status="not_running")


@router.post("/oauth2/callback-server/stop")
async def stop_callback_server() -> dict[str, str]:
    """Stop the callback server if it's running."""
    with _cb.lock:
        if _cb.server is not None:
            try:
                _cb.server.server_close()
            except Exception:
                pass
            _cb.server = None
        # Mark as not running so the thread exits on next loop iteration
        _cb.received = True
    return {"status": "stopped"}


@router.post("/oauth2/token", response_model=OAuth2TokenResponse)
async def exchange_token(req: OAuth2TokenRequest) -> OAuth2TokenResponse:
    """Exchange an authorization code for tokens, with optional PKCE."""
    form_data: dict[str, str] = {
        "grant_type": req.grant_type,
        "code": req.code,
        "client_id": req.client_id,
    }
    if req.client_secret:
        form_data["client_secret"] = req.client_secret
    if req.redirect_uri:
        form_data["redirect_uri"] = req.redirect_uri
    if req.scope:
        form_data["scope"] = req.scope
    if req.code_verifier:
        form_data["code_verifier"] = req.code_verifier

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(req.token_url, data=form_data)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502, detail=f"token endpoint unreachable: {exc}"
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"token endpoint error: {response.text}",
        )

    try:
        body = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"invalid JSON from token endpoint: {exc}"
        ) from exc

    if "access_token" not in body:
        raise HTTPException(
            status_code=502,
            detail=f"no access_token in response: {body}",
        )

    return OAuth2TokenResponse(
        access_token=body["access_token"],
        token_type=body.get("token_type", "Bearer"),
        expires_in=body.get("expires_in"),
        refresh_token=body.get("refresh_token"),
        scope=body.get("scope"),
        raw=body,
    )


class OAuth2RefreshRequest(BaseModel):
    """Parameters for the OAuth2 refresh_token grant."""

    token_url: str = Field(..., min_length=1)
    refresh_token: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: str = ""
    scope: str = ""


@router.post("/oauth2/refresh", response_model=OAuth2TokenResponse)
async def refresh_token(req: OAuth2RefreshRequest) -> OAuth2TokenResponse:
    """Use a refresh token to obtain a new access token.

    Implements RFC 6749 §6 refresh token rotation: if the authorization server
    returns a new refresh_token in the response, it is included in the output
    so the caller can persist it and discard the old one.
    """
    form_data: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": req.refresh_token,
        "client_id": req.client_id,
    }
    if req.client_secret:
        form_data["client_secret"] = req.client_secret
    if req.scope:
        form_data["scope"] = req.scope

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(req.token_url, data=form_data)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502, detail=f"token endpoint unreachable: {exc}"
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"token endpoint error: {response.text}",
        )

    try:
        body = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"invalid JSON from token endpoint: {exc}"
        ) from exc

    if "access_token" not in body:
        raise HTTPException(
            status_code=502,
            detail=f"no access_token in response: {body}",
        )

    # RFC 6749 §6: server MAY issue a new refresh token — store the new one if
    # present, otherwise fall back to the original so caller always has a value.
    rotated_refresh = body.get("refresh_token") or req.refresh_token

    return OAuth2TokenResponse(
        access_token=body["access_token"],
        token_type=body.get("token_type", "Bearer"),
        expires_in=body.get("expires_in"),
        refresh_token=rotated_refresh,
        scope=body.get("scope"),
        raw=body,
    )


# ---------------------------------------------------------------------------
# Client Credentials grant (server-to-server, P0)
# ---------------------------------------------------------------------------


class OAuth2ClientCredentialsRequest(BaseModel):
    """Parameters for the OAuth2 client_credentials grant."""

    token_url: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)
    scope: str = ""
    # Extra parameters forwarded verbatim (e.g. audience for Auth0/Okta)
    extra_params: dict[str, str] = Field(default_factory=dict)
    # If True, send credentials as HTTP Basic Auth header instead of form body
    use_basic_auth: bool = False


class OAuth2ClientCredentialsResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    scope: str | None = None
    # Unix timestamp when the token expires (None if expires_in not provided)
    expires_at: float | None = None
    raw: dict[str, object] = Field(default_factory=dict)


@router.post(
    "/oauth2/client-credentials",
    response_model=OAuth2ClientCredentialsResponse,
)
async def client_credentials(
    req: OAuth2ClientCredentialsRequest,
) -> OAuth2ClientCredentialsResponse:
    """Obtain an access token via the Client Credentials grant.

    This is the correct grant for server-to-server integrations (no user
    involvement). Credentials are sent either as HTTP Basic Auth (RFC 6749 §2.3.1
    recommended) or as form body fields — controlled by `use_basic_auth`.
    """
    form_data: dict[str, str] = {"grant_type": "client_credentials"}
    if req.scope:
        form_data["scope"] = req.scope
    form_data.update(req.extra_params)

    headers: dict[str, str] = {}
    if req.use_basic_auth:
        # RFC 6749 §2.3.1 — preferred method
        creds = base64.b64encode(
            f"{req.client_id}:{req.client_secret}".encode("utf-8")
        ).decode("ascii")
        headers["Authorization"] = f"Basic {creds}"
    else:
        form_data["client_id"] = req.client_id
        form_data["client_secret"] = req.client_secret

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                req.token_url, data=form_data, headers=headers
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502, detail=f"token endpoint unreachable: {exc}"
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"token endpoint error: {response.text}",
        )

    try:
        body = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"invalid JSON from token endpoint: {exc}"
        ) from exc

    if "access_token" not in body:
        raise HTTPException(
            status_code=502,
            detail=f"no access_token in response: {body}",
        )

    expires_in: int | None = body.get("expires_in")
    expires_at: float | None = (
        time.time() + expires_in if expires_in is not None else None
    )

    return OAuth2ClientCredentialsResponse(
        access_token=body["access_token"],
        token_type=body.get("token_type", "Bearer"),
        expires_in=expires_in,
        scope=body.get("scope"),
        expires_at=expires_at,
        raw=body,
    )


# ---------------------------------------------------------------------------
# Token reuse / auto-refresh helper
# ---------------------------------------------------------------------------


class TokenReuseRequest(BaseModel):
    """Check if a cached token is still valid; auto-refresh if not.

    The caller passes the token details from env vars. The sidecar decides
    whether the token is still usable, needs refresh, or requires a new grant.
    """

    access_token: str = ""
    refresh_token: str = ""
    expires_at: float | None = None  # Unix timestamp
    token_url: str = ""
    client_id: str = ""
    client_secret: str = ""
    scope: str = ""
    # Safety margin: treat token as expired this many seconds before actual expiry
    expiry_buffer_seconds: int = 60


class TokenReuseResponse(BaseModel):
    status: str  # "valid" | "refreshed" | "expired" | "unknown"
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float | None = None
    message: str = ""


@router.post("/oauth2/token-reuse", response_model=TokenReuseResponse)
async def token_reuse(req: TokenReuseRequest) -> TokenReuseResponse:
    """Return a valid access token, auto-refreshing if expired.

    Decision logic:
    1. If `expires_at` is set and token has at least `expiry_buffer_seconds`
       left → return as-is (status: "valid").
    2. If `expires_at` is not set but `access_token` is non-empty → assume valid
       (status: "valid" / "unknown").
    3. If expired and `refresh_token` + `token_url` are provided → attempt
       refresh (status: "refreshed").
    4. Otherwise → caller must obtain a new token (status: "expired").
    """
    now = time.time()

    def _is_valid() -> bool:
        if not req.access_token:
            return False
        if req.expires_at is None:
            return True  # No expiry info — optimistically assume valid
        return req.expires_at - req.expiry_buffer_seconds > now

    if _is_valid():
        return TokenReuseResponse(
            status="valid" if req.expires_at is not None else "unknown",
            access_token=req.access_token,
            refresh_token=req.refresh_token,
            expires_at=req.expires_at,
            message="token is still valid",
        )

    # Token expired or missing — try refresh
    if req.refresh_token and req.token_url and req.client_id:
        try:
            refresh_resp = await refresh_token(
                OAuth2RefreshRequest(
                    token_url=req.token_url,
                    refresh_token=req.refresh_token,
                    client_id=req.client_id,
                    client_secret=req.client_secret,
                    scope=req.scope,
                )
            )
            new_expires_at: float | None = (
                time.time() + refresh_resp.expires_in
                if refresh_resp.expires_in is not None
                else None
            )
            return TokenReuseResponse(
                status="refreshed",
                access_token=refresh_resp.access_token,
                refresh_token=refresh_resp.refresh_token or req.refresh_token,
                expires_at=new_expires_at,
                message="token refreshed successfully",
            )
        except HTTPException as exc:
            return TokenReuseResponse(
                status="expired",
                message=f"refresh failed: {exc.detail}",
            )

    return TokenReuseResponse(
        status="expired",
        message="token expired and no refresh token available",
    )


# ---------------------------------------------------------------------------
# Resource Owner Password Credentials grant (DEPRECATED by OAuth 2.1)
# ---------------------------------------------------------------------------


class OAuth2PasswordRequest(BaseModel):
    """Parameters for the OAuth2 password grant.

    WARNING: This grant type is deprecated in OAuth 2.1 (draft-ietf-oauth-v2-1)
    and should NOT be used for new integrations. It is provided here solely for
    compatibility with legacy authorization servers that have not migrated.
    """

    token_url: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    client_secret: str = ""
    scope: str = ""


@router.post("/oauth2/password", response_model=OAuth2TokenResponse)
async def password_grant(req: OAuth2PasswordRequest) -> OAuth2TokenResponse:
    """OAuth2 Resource Owner Password Credentials grant.

    DEPRECATED: This grant type has been removed in OAuth 2.1. It exposes
    user credentials directly to the client application and should be replaced
    with Authorization Code + PKCE wherever possible. Included for legacy
    system compatibility only — do not use for new integrations.
    """
    form_data: dict[str, str] = {
        "grant_type": "password",
        "username": req.username,
        "password": req.password,
        "client_id": req.client_id,
    }
    if req.client_secret:
        form_data["client_secret"] = req.client_secret
    if req.scope:
        form_data["scope"] = req.scope

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(req.token_url, data=form_data)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502, detail=f"token endpoint unreachable: {exc}"
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"token endpoint error: {response.text}",
        )

    try:
        body = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"invalid JSON from token endpoint: {exc}"
        ) from exc

    if "access_token" not in body:
        raise HTTPException(
            status_code=502,
            detail=f"no access_token in response: {body}",
        )

    return OAuth2TokenResponse(
        access_token=body["access_token"],
        token_type=body.get("token_type", "Bearer"),
        expires_in=body.get("expires_in"),
        refresh_token=body.get("refresh_token"),
        scope=body.get("scope"),
        raw=body,
    )
