"""HTTP request execution endpoint — REST first, more protocols to follow."""

from __future__ import annotations

import base64
import time
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import cookies, environments, storage
from ..models import AuthConfig

router = APIRouter(prefix="/api/requests", tags=["requests"])

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class ExecuteRequest(BaseModel):
    method: HttpMethod = "GET"
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    auth: AuthConfig | None = None
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    follow_redirects: bool = True
    environment_id: str | None = None
    collection_id: str | None = None
    client_cert: str | None = None
    client_key: str | None = None
    ca_bundle_path: str | None = None
    verify_ssl: bool = True


class TimingBreakdown(BaseModel):
    dns_ms: float = 0
    connect_ms: float = 0
    tls_ms: float = 0
    server_processing_ms: float = 0
    transfer_ms: float = 0
    total_ms: float = 0


class _TimingCollector:
    """Collects per-phase timing via httpcore trace events."""

    def __init__(self) -> None:
        self.marks: dict[str, float] = {}
        self.dns_ms: float = 0
        self.connect_ms: float = 0
        self.tls_ms: float = 0
        self.server_processing_ms: float = 0
        self.transfer_ms: float = 0

    async def trace(self, name: str, info: dict) -> None:  # noqa: ARG002, ANN401
        now = time.perf_counter()
        if name == "connection.connect_tcp.started":
            self.marks["tcp_start"] = now
        elif name == "connection.connect_tcp.complete":
            self.connect_ms = (now - self.marks.get("tcp_start", now)) * 1000
        elif name == "connection.start_tls.started":
            self.marks["tls_start"] = now
        elif name == "connection.start_tls.complete":
            self.tls_ms = (now - self.marks.get("tls_start", now)) * 1000
        elif name == "http11.send_request_headers.started":
            self.marks["send_start"] = now
        elif name == "http11.send_request_body.complete":
            self.marks["send_done"] = now
        elif name == "http11.receive_response_headers.started":
            # Fallback: if send_done not set, use send_start
            self.marks.setdefault("send_done", self.marks.get("send_start", now))
        elif name == "http11.receive_response_headers.complete":
            self.server_processing_ms = (
                now - self.marks.get("send_done", self.marks.get("send_start", now))
            ) * 1000
            self.marks["headers_done"] = now
        elif name == "http11.receive_response_body.complete":
            self.transfer_ms = (now - self.marks.get("headers_done", now)) * 1000
        # HTTP/2 equivalents
        elif name == "http2.send_request_headers.started":
            self.marks["send_start"] = now
        elif name == "http2.send_request_body.complete":
            self.marks["send_done"] = now
        elif name == "http2.receive_response_headers.started":
            self.marks.setdefault("send_done", self.marks.get("send_start", now))
        elif name == "http2.receive_response_headers.complete":
            self.server_processing_ms = (
                now - self.marks.get("send_done", self.marks.get("send_start", now))
            ) * 1000
            self.marks["headers_done"] = now
        elif name == "http2.receive_response_body.complete":
            self.transfer_ms = (now - self.marks.get("headers_done", now)) * 1000


class ExecuteResponse(BaseModel):
    status: int
    status_text: str
    headers: dict[str, str]
    body: str
    body_size_bytes: int
    elapsed_ms: float
    timing: TimingBreakdown | None = None
    final_url: str
    resolved_url: str | None = None
    cookies: dict[str, str] = Field(default_factory=dict)


def _apply_auth(
    auth: AuthConfig,
    headers: dict[str, str],
    query: dict[str, str],
    env: environments.Environment | None,
    collection_vars: dict[str, str] | None = None,
) -> None:
    """Mutate *headers* or *query* in place to inject auth credentials."""
    sub = lambda v: environments.substitute(v, env, collection_vars=collection_vars) if v else ""  # noqa: E731
    if auth.type == "bearer":
        headers["Authorization"] = f"Bearer {sub(auth.token)}"
    elif auth.type == "basic":
        creds = base64.b64encode(
            f"{sub(auth.username)}:{sub(auth.password)}".encode()
        ).decode()
        headers["Authorization"] = f"Basic {creds}"
    elif auth.type == "apikey":
        key = sub(auth.key)
        value = sub(auth.value)
        if key:
            if auth.add_to == "query":
                query[key] = value
            else:
                headers[key] = value


@router.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest, http_request: Request) -> ExecuteResponse:
    # Resolve {{var}} placeholders against the chosen environment, if any.
    env = environments.get(req.environment_id) if req.environment_id else None
    if req.environment_id and env is None:
        raise HTTPException(status_code=404, detail="environment not found")

    # Extract collection-level variables when a collection_id is provided.
    coll_vars: dict[str, str] | None = None
    if req.collection_id:
        coll = storage.get(req.collection_id)
        if coll is not None:
            coll_vars = {v.name: v.value for v in coll.variables if v.enabled}

    resolved_url = environments.substitute(req.url, env, collection_vars=coll_vars)
    resolved_headers = environments.substitute_dict(req.headers, env, collection_vars=coll_vars)
    resolved_body = (
        environments.substitute(req.body, env, collection_vars=coll_vars) if req.body is not None else None
    )
    resolved_query = environments.substitute_dict(req.query, env, collection_vars=coll_vars)

    # Inject authentication into headers/query.
    if req.auth and req.auth.type != "none":
        _apply_auth(req.auth, resolved_headers, resolved_query, env, collection_vars=coll_vars)

    # Load persisted cookies for this environment.
    jar = cookies.load(req.environment_id) if req.environment_id else None
    httpx_cookies = cookies.to_httpx_cookies(jar) if jar and jar.cookies else None

    # Build optional SSL client certificate tuple.
    cert_pair: tuple[str, str] | None = None
    if req.client_cert and req.client_key:
        cert_pair = (req.client_cert, req.client_key)
    elif req.client_cert:
        cert_pair = (req.client_cert, req.client_cert)

    # Resolve SSL verification: ca_bundle_path > verify_ssl toggle > default.
    ssl_verify: bool | str = True
    if not req.verify_ssl:
        ssl_verify = False
    elif req.ca_bundle_path:
        from pathlib import Path
        ca_path = Path(req.ca_bundle_path).expanduser().resolve()
        if not ca_path.is_file():
            raise HTTPException(status_code=400, detail=f"CA bundle not found: {req.ca_bundle_path}")
        ssl_verify = str(ca_path)

    # Set up timing collector for httpcore trace events.
    collector = _TimingCollector()

    # Backend-2/3: use the shared lifespan-managed client when possible
    # (no custom SSL). Per-request client is created only when custom SSL
    # settings are needed (cert, ca_bundle, disabled verify).
    _needs_custom_ssl = cert_pair is not None or ssl_verify is not True
    shared_client: httpx.AsyncClient | None = getattr(
        getattr(http_request.app, "state", None), "http_client", None
    )
    use_shared = not _needs_custom_ssl and shared_client is not None

    started = time.perf_counter()
    try:
        if use_shared:
            # Shared pooled client — no context manager needed.
            _client = shared_client
            request = _client.build_request(  # type: ignore[union-attr]
                method=req.method,
                url=resolved_url,
                headers=resolved_headers,
                params=resolved_query or None,
                content=resolved_body.encode("utf-8") if resolved_body is not None else None,
            )
            request.extensions["trace"] = collector.trace
            response = await _client.send(  # type: ignore[union-attr]
                request,
                follow_redirects=req.follow_redirects,
                cookies=httpx_cookies,
                auth=None,
                timeout=req.timeout_seconds,
            )
        else:
            # Per-request client with custom SSL settings.
            transport = httpx.AsyncHTTPTransport(http2=True)
            async with httpx.AsyncClient(
                transport=transport,
                timeout=req.timeout_seconds,
                follow_redirects=req.follow_redirects,
                cookies=httpx_cookies,
                cert=cert_pair,
                verify=ssl_verify,
            ) as client:
                request = client.build_request(
                    method=req.method,
                    url=resolved_url,
                    headers=resolved_headers,
                    params=resolved_query or None,
                    content=resolved_body.encode("utf-8") if resolved_body is not None else None,
                )
                request.extensions["trace"] = collector.trace
                response = await client.send(request)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"transport error: {exc}") from exc

    finished = time.perf_counter()
    elapsed_ms = (finished - started) * 1000

    # Build timing breakdown from collector.
    # DNS is approximated: total minus all measured phases.
    measured = collector.connect_ms + collector.tls_ms + collector.server_processing_ms + collector.transfer_ms
    dns_ms = max(0, elapsed_ms - measured) if measured > 0 else 0

    timing = TimingBreakdown(
        dns_ms=round(dns_ms, 2),
        connect_ms=round(collector.connect_ms, 2),
        tls_ms=round(collector.tls_ms, 2),
        server_processing_ms=round(collector.server_processing_ms, 2),
        transfer_ms=round(collector.transfer_ms, 2),
        total_ms=round(elapsed_ms, 2),
    )

    # Persist response cookies back to the jar.
    response_cookies = dict(response.cookies)
    if jar and req.environment_id:
        updated_jar = cookies.from_httpx_response(
            req.environment_id, jar, response_cookies,
        )
        cookies.save(updated_jar)

    return ExecuteResponse(
        status=response.status_code,
        status_text=response.reason_phrase or "",
        headers=dict(response.headers),
        body=response.text,
        body_size_bytes=len(response.content),
        elapsed_ms=round(elapsed_ms, 2),
        timing=timing,
        final_url=str(response.url),
        resolved_url=resolved_url if env is not None else None,
        cookies=response_cookies,
    )
