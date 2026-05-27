"""Agentic API Explorer — autonomously discovers, probes, and analyses APIs."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import storage
from ..models import Collection, CollectionItem

router = APIRouter(prefix="/api/agent", tags=["agent"])

# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------


class ExploreInput(BaseModel):
    base_url: str
    max_requests: int = Field(default=20, ge=1, le=100)
    methods: list[str] = Field(default=["GET", "POST", "PUT", "PATCH", "DELETE"])
    headers: dict[str, str] = Field(default_factory=dict)
    save_as_collection: bool = True
    collection_name: str | None = None


class ExploreIssue(BaseModel):
    severity: str  # "error", "warning", "info"
    message: str
    endpoint: str


class ExploredEndpoint(BaseModel):
    method: str
    path: str
    status: int | None = None
    elapsed_ms: float = 0.0
    size_bytes: int = 0
    content_type: str = ""
    issues: list[str] = Field(default_factory=list)
    body_preview: str = ""


class ExploreResult(BaseModel):
    endpoints_discovered: int
    requests_sent: int
    issues: list[ExploreIssue] = Field(default_factory=list)
    endpoints: list[ExploredEndpoint] = Field(default_factory=list)
    collection_id: str | None = None
    elapsed_ms: float = 0.0


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

OPENAPI_PATHS = [
    "/openapi.json",
    "/swagger.json",
    "/api-docs",
    "/openapi.yaml",
    "/swagger/v1/swagger.json",
]

COMMON_PATHS = [
    "/",
    "/api",
    "/health",
    "/api/v1",
    "/rest",
    "/graphql",
    "/soap",
]


def _normalise_base(url: str) -> str:
    """Ensure base URL ends without a trailing slash."""
    return url.rstrip("/")


async def _try_openapi(
    client: httpx.AsyncClient,
    base: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Try standard OpenAPI spec locations. Return (spec_dict, spec_url)."""
    for path in OPENAPI_PATHS:
        url = base + path
        try:
            r = await client.get(url, timeout=5)
            if r.status_code == 200:
                ct = r.headers.get("content-type", "")
                if "json" in ct or "yaml" in ct or path.endswith(".json"):
                    try:
                        spec = r.json()
                        if isinstance(spec, dict) and ("paths" in spec or "openapi" in spec or "swagger" in spec):
                            return spec, url
                    except Exception:
                        pass
        except (httpx.HTTPError, httpx.TimeoutException):
            continue
    return None, None


def _extract_openapi_endpoints(
    spec: dict[str, Any],
    allowed_methods: list[str],
) -> list[tuple[str, str, dict[str, Any] | None]]:
    """Return [(method, path, request_body_schema)] from an OpenAPI spec."""
    endpoints: list[tuple[str, str, dict[str, Any] | None]] = []
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return endpoints
    for path, ops in paths.items():
        if not isinstance(ops, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            if method.upper() not in allowed_methods:
                continue
            if method in ops:
                schema = None
                op = ops[method]
                if isinstance(op, dict):
                    rb = op.get("requestBody", {})
                    if isinstance(rb, dict):
                        content = rb.get("content", {})
                        if isinstance(content, dict):
                            json_ct = content.get("application/json", {})
                            if isinstance(json_ct, dict):
                                schema = json_ct.get("schema")
                endpoints.append((method.upper(), path, schema))
    return endpoints


async def _discover_common(
    client: httpx.AsyncClient,
    base: str,
) -> list[tuple[str, str]]:
    """Probe common paths via GET, return those that respond."""
    found: list[tuple[str, str]] = []
    for path in COMMON_PATHS:
        url = base + path
        try:
            r = await client.get(url, timeout=5)
            if r.status_code < 500:
                found.append(("GET", path))
                # Try to find links in JSON responses.
                try:
                    body = r.json()
                    if isinstance(body, dict):
                        for v in body.values():
                            if isinstance(v, str) and v.startswith("/"):
                                found.append(("GET", v))
                except Exception:
                    pass
        except (httpx.HTTPError, httpx.TimeoutException):
            continue
    return found


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------

def _generate_body(schema: dict[str, Any] | None) -> str | None:
    """Generate a minimal JSON body from an OpenAPI schema, or fallback to {}."""
    if schema is None:
        return "{}"
    # Very basic: walk required properties and produce stub values.
    if schema.get("type") == "object":
        props = schema.get("properties", {})
        required = schema.get("required", [])
        obj: dict[str, Any] = {}
        for name, prop in props.items():
            if not isinstance(prop, dict):
                continue
            if name in required or len(obj) < 3:
                t = prop.get("type", "string")
                if t == "string":
                    obj[name] = "string"
                elif t == "integer":
                    obj[name] = 0
                elif t == "number":
                    obj[name] = 0.0
                elif t == "boolean":
                    obj[name] = False
                elif t == "array":
                    obj[name] = []
                else:
                    obj[name] = None
        import json as _json
        return _json.dumps(obj)
    return "{}"


async def _probe_endpoint(
    client: httpx.AsyncClient,
    base: str,
    method: str,
    path: str,
    headers: dict[str, str],
    schema: dict[str, Any] | None = None,
) -> ExploredEndpoint:
    """Send a single request, record the result."""
    url = base + path
    kwargs: dict[str, Any] = {"timeout": 10, "headers": dict(headers)}
    body: str | None = None

    if method in ("POST", "PUT", "PATCH"):
        body = _generate_body(schema)
        kwargs["content"] = body
        kwargs["headers"]["Content-Type"] = "application/json"

    ep = ExploredEndpoint(method=method, path=path)
    t0 = time.monotonic()
    try:
        r = await client.request(method, url, **kwargs)
        elapsed = (time.monotonic() - t0) * 1000
        ep.status = r.status_code
        ep.elapsed_ms = round(elapsed, 1)
        ep.size_bytes = len(r.content)
        ep.content_type = r.headers.get("content-type", "")
        # Body preview — first 500 chars.
        try:
            ep.body_preview = r.text[:500]
        except Exception:
            ep.body_preview = "(binary)"
    except httpx.TimeoutException:
        ep.elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        ep.issues.append("Timeout")
    except httpx.HTTPError as exc:
        ep.elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        ep.issues.append(f"Connection error: {exc}")

    return ep


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _analyse(
    endpoints: list[ExploredEndpoint],
    base: str,
) -> list[ExploreIssue]:
    """Detect issues and patterns across probed endpoints."""
    issues: list[ExploreIssue] = []
    content_types_on_errors: set[str] = set()

    for ep in endpoints:
        label = f"{ep.method} {ep.path}"

        if ep.status is not None and ep.status >= 500:
            issues.append(ExploreIssue(severity="error", message=f"Server error on {label}", endpoint=label))

        if ep.elapsed_ms > 2000:
            issues.append(ExploreIssue(severity="warning", message=f"Slow endpoint: {ep.elapsed_ms:.0f}ms", endpoint=label))

        if ep.status is not None and ep.status < 400:
            # Check missing CORS headers.
            # We only flag this as info since our own requests won't carry
            # an Origin header so the server might legitimately omit them.
            pass  # CORS checked below if we had response headers — skipped in MVP

            if not ep.content_type:
                issues.append(ExploreIssue(severity="info", message="No Content-Type header", endpoint=label))

        # Detect open mutating endpoints (no 401/403).
        if ep.method in ("POST", "PUT", "PATCH", "DELETE"):
            if ep.status is not None and ep.status not in (401, 403):
                issues.append(ExploreIssue(severity="warning", message=f"No auth on {label}", endpoint=label))

        # Track error response format consistency.
        if ep.status is not None and ep.status >= 400:
            ct = ep.content_type.split(";")[0].strip().lower() if ep.content_type else "none"
            content_types_on_errors.add(ct)

        # Propagate probe-level issues to the issue list.
        for issue_text in ep.issues:
            issues.append(ExploreIssue(severity="error", message=issue_text, endpoint=label))

    # Mixed error formats.
    if len(content_types_on_errors) > 1:
        issues.append(ExploreIssue(
            severity="warning",
            message=f"Mixed error format ({', '.join(sorted(content_types_on_errors))})",
            endpoint="(multiple)",
        ))

    # Detect patterns (informational).
    paths = [ep.path for ep in endpoints]
    if any(re.search(r"/v\d+", p) for p in paths):
        issues.append(ExploreIssue(severity="info", message="API versioning detected (vN in URL)", endpoint="(pattern)"))
    if any("page" in p.lower() or "offset" in p.lower() or "limit" in p.lower() for p in paths):
        issues.append(ExploreIssue(severity="info", message="Pagination parameters detected", endpoint="(pattern)"))

    return issues


# ---------------------------------------------------------------------------
# Collection generation
# ---------------------------------------------------------------------------

def _build_collection(
    name: str,
    base: str,
    endpoints: list[ExploredEndpoint],
) -> Collection:
    """Create a Collection from explored endpoints, grouping by path prefix."""
    coll_id = str(uuid.uuid4())

    # Group endpoints by first path segment.
    folders: dict[str, list[ExploredEndpoint]] = {}
    for ep in endpoints:
        parts = [p for p in ep.path.split("/") if p]
        prefix = parts[0] if parts else "_root"
        folders.setdefault(prefix, []).append(ep)

    items: list[CollectionItem] = []
    for folder_name, eps in folders.items():
        if len(eps) == 1 and folder_name == "_root":
            ep = eps[0]
            items.append(CollectionItem(
                id=str(uuid.uuid4()),
                name=f"{ep.method} {ep.path}",
                method=ep.method,  # type: ignore[arg-type]
                url=base + ep.path,
                headers={},
            ))
        else:
            folder_items = [
                CollectionItem(
                    id=str(uuid.uuid4()),
                    name=f"{ep.method} {ep.path}",
                    method=ep.method,  # type: ignore[arg-type]
                    url=base + ep.path,
                    headers={},
                )
                for ep in eps
            ]
            items.append(CollectionItem(
                id=str(uuid.uuid4()),
                name=folder_name,
                is_folder=True,
                items=folder_items,
            ))

    return Collection(id=coll_id, name=name, items=items)


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

@router.post("/explore", response_model=ExploreResult)
async def explore(body: ExploreInput) -> ExploreResult:
    base = _normalise_base(body.base_url)
    allowed = [m.upper() for m in body.methods]
    t0 = time.monotonic()

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # 1. Discovery
        discovered: list[tuple[str, str, dict[str, Any] | None]] = []

        spec, spec_url = await _try_openapi(client, base)
        if spec:
            discovered = _extract_openapi_endpoints(spec, allowed)

        if not discovered:
            common = await _discover_common(client, base)
            discovered = [(m, p, None) for m, p in common]

        # Deduplicate.
        seen: set[tuple[str, str]] = set()
        unique: list[tuple[str, str, dict[str, Any] | None]] = []
        for m, p, s in discovered:
            key = (m, p)
            if key not in seen:
                seen.add(key)
                unique.append((m, p, s))
        discovered = unique

        # Cap at max_requests.
        discovered = discovered[:body.max_requests]

        # 2. Probing
        probed: list[ExploredEndpoint] = []
        for method, path, schema in discovered:
            ep = await _probe_endpoint(client, base, method, path, body.headers, schema)
            probed.append(ep)

    # 3. Analysis
    issues = _analyse(probed, base)

    # 4. Collection generation
    collection_id: str | None = None
    if body.save_as_collection and probed:
        coll_name = body.collection_name or f"Explored: {urlparse(base).netloc}"
        coll = _build_collection(coll_name, base, probed)
        storage._atomic_write(coll)
        collection_id = coll.id

    elapsed = (time.monotonic() - t0) * 1000
    return ExploreResult(
        endpoints_discovered=len(discovered),
        requests_sent=len(probed),
        issues=issues,
        endpoints=probed,
        collection_id=collection_id,
        elapsed_ms=round(elapsed, 1),
    )
