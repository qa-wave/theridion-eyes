"""Theridion MCP server — official SDK (FastMCP) implementation.

Exposes Theridion capabilities as MCP tools, resources, and prompts
for Claude Desktop and other MCP-compatible clients. Communicates via
stdio transport (no HTTP sidecar needed).

Never prints to stdout in stdio mode — all logging goes to stderr.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

# Route logging to stderr so it never contaminates the stdio transport.
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("theridion.mcp")

mcp = FastMCP(
    "Theridion",
    instructions="API testing platform — execute requests, manage collections, run tests",
)


# ---------------------------------------------------------------------------
# Tool 1: execute_request
# ---------------------------------------------------------------------------


@mcp.tool()
async def execute_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    environment_id: str | None = None,
) -> dict[str, Any]:
    """Execute an HTTP request and return the response. Supports GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS.

    Args:
        method: HTTP method (GET, POST, PUT, etc.)
        url: Full URL to send the request to
        headers: Optional request headers as key-value pairs
        body: Optional request body (JSON string for POST/PUT/PATCH)
        environment_id: Optional environment ID for variable substitution ({{var}} syntax)
    """
    from . import environments

    import httpx

    env = environments.get(environment_id) if environment_id else None
    resolved_url = environments.substitute(url, env) if env else url
    resolved_headers = (
        environments.substitute_dict(headers, env) if env and headers else (headers or {})
    )
    resolved_body = environments.substitute(body, env) if env and body else body

    try:
        async with httpx.AsyncClient(
            http2=True, timeout=30, follow_redirects=True,
        ) as client:
            response = await client.request(
                method=method.upper(),
                url=resolved_url,
                headers=resolved_headers,
                content=resolved_body.encode("utf-8") if resolved_body else None,
            )
        return {
            "status": response.status_code,
            "headers": dict(response.headers),
            "body": response.text[:5000],
            "elapsed_ms": round(response.elapsed.total_seconds() * 1000, 2),
        }
    except httpx.RequestError as exc:
        return {"error": f"transport error: {exc}"}


# ---------------------------------------------------------------------------
# Tool 2: list_collections
# ---------------------------------------------------------------------------


@mcp.tool()
def list_collections() -> list[dict[str, Any]]:
    """List all saved API collections with their request counts."""
    from . import storage

    summaries = storage.list_summaries()
    return [
        {"id": s.id, "name": s.name, "request_count": s.request_count}
        for s in summaries
    ]


# ---------------------------------------------------------------------------
# Tool 3: get_collection
# ---------------------------------------------------------------------------


@mcp.tool()
def get_collection(collection_id: str) -> dict[str, Any]:
    """Get full details of a collection including all requests and folders.

    Args:
        collection_id: UUID of the collection to retrieve
    """
    from . import storage

    coll = storage.get(collection_id)
    if not coll:
        return {"error": "Collection not found"}
    return coll.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Tool 4: run_collection
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_collection(
    collection_id: str,
    environment_id: str | None = None,
) -> dict[str, Any]:
    """Run all requests in a collection sequentially and return results with assertion outcomes.

    Args:
        collection_id: UUID of the collection to run
        environment_id: Optional environment ID for variable substitution
    """
    from . import environments, storage
    from .assertions import ResponseData, evaluate_all
    from .models import CollectionItem

    import httpx

    coll = storage.get(collection_id)
    if coll is None:
        return {"error": "Collection not found"}

    env = environments.get(environment_id) if environment_id else None
    if environment_id and env is None:
        return {"error": "Environment not found"}

    coll_vars: dict[str, str] | None = None
    if coll.variables:
        enabled = {v.name: v.value for v in coll.variables if v.enabled}
        if enabled:
            coll_vars = enabled

    def _collect_requests(items: list[CollectionItem]) -> list[CollectionItem]:
        out: list[CollectionItem] = []
        for it in items:
            if it.is_folder:
                out.extend(_collect_requests(it.items))
            else:
                out.append(it)
        return out

    requests = _collect_requests(coll.items)
    results: list[dict[str, Any]] = []
    total_elapsed = 0.0
    successful = 0

    for req in requests:
        if not req.url:
            results.append({
                "request_name": req.name,
                "method": req.method or "GET",
                "url": "",
                "error": "No URL specified",
            })
            continue

        resolved_url = environments.substitute(req.url, env, collection_vars=coll_vars)
        resolved_headers = environments.substitute_dict(
            req.headers, env, collection_vars=coll_vars,
        )
        resolved_body = (
            environments.substitute(req.body, env, collection_vars=coll_vars)
            if req.body else None
        )

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                http2=True, timeout=30, follow_redirects=True,
            ) as client:
                response = await client.request(
                    method=req.method or "GET",
                    url=resolved_url,
                    headers=resolved_headers,
                    content=resolved_body.encode("utf-8") if resolved_body else None,
                )
            elapsed = (time.perf_counter() - started) * 1000

            a_results_list = []
            if req.assertions:
                resp_data = ResponseData(
                    status=response.status_code,
                    headers=dict(response.headers),
                    body=response.text,
                    elapsed_ms=elapsed,
                )
                a_results_list = evaluate_all(req.assertions, resp_data)

            a_passed = sum(1 for r in a_results_list if r.passed)
            results.append({
                "request_name": req.name,
                "method": req.method or "GET",
                "url": req.url,
                "status": response.status_code,
                "elapsed_ms": round(elapsed, 2),
                "assertions_passed": a_passed,
                "assertions_failed": len(a_results_list) - a_passed,
            })
            successful += 1
            total_elapsed += elapsed
        except httpx.RequestError as exc:
            elapsed = (time.perf_counter() - started) * 1000
            results.append({
                "request_name": req.name,
                "method": req.method or "GET",
                "url": req.url,
                "error": f"transport error: {exc}",
                "elapsed_ms": round(elapsed, 2),
            })
            total_elapsed += elapsed

    return {
        "collection_name": coll.name,
        "total_requests": len(requests),
        "successful_requests": successful,
        "failed_requests": len(requests) - successful,
        "total_elapsed_ms": round(total_elapsed, 2),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Tool 5: list_environments
# ---------------------------------------------------------------------------


@mcp.tool()
def list_environments() -> list[dict[str, Any]]:
    """List all saved environments with their variable counts."""
    from . import environments

    return [
        {"id": s.id, "name": s.name, "variable_count": s.variable_count}
        for s in environments.list_summaries()
    ]


# ---------------------------------------------------------------------------
# Tool 6: create_request
# ---------------------------------------------------------------------------


@mcp.tool()
def create_request(
    collection_id: str,
    name: str,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    """Save a new request to an existing collection.

    Args:
        collection_id: UUID of the collection to add the request to
        name: Human-readable name for the request
        method: HTTP method (GET, POST, etc.)
        url: Full URL for the request
        headers: Optional request headers
        body: Optional request body
    """
    import uuid

    from . import storage
    from .models import CollectionItem

    coll = storage.get(collection_id)
    if coll is None:
        return {"error": "Collection not found"}

    item = CollectionItem(
        id=str(uuid.uuid4()),
        name=name,
        method=method.upper(),  # type: ignore[arg-type]
        url=url,
        headers=headers or {},
        body=body,
    )
    updated = storage.add_request(collection_id, item)
    return {"id": item.id, "name": item.name, "collection": updated.name}


# ---------------------------------------------------------------------------
# Tool 7: inspect_api
# ---------------------------------------------------------------------------


@mcp.tool()
async def inspect_api(base_url: str) -> dict[str, Any]:
    """Discover and inspect an API by checking for OpenAPI/Swagger specs and probing common endpoints.

    Args:
        base_url: Base URL of the API to inspect (e.g. http://localhost:4010)
    """
    import httpx

    base = base_url.rstrip("/")
    discovery_paths = [
        "/openapi.json",
        "/swagger.json",
        "/api-docs",
        "/docs",
        "/api/v1",
        "/api/v2",
        "/api/health",
        "/health",
        "/api",
    ]

    found: list[dict[str, Any]] = []
    openapi_spec: dict[str, Any] | None = None

    try:
        async with httpx.AsyncClient(
            http2=True, timeout=10, follow_redirects=True,
        ) as client:
            for path in discovery_paths:
                try:
                    resp = await client.get(f"{base}{path}")
                    entry: dict[str, Any] = {
                        "path": path,
                        "status": resp.status_code,
                        "content_type": resp.headers.get("content-type", ""),
                    }
                    if resp.status_code < 400:
                        # Try to parse as OpenAPI spec.
                        if path in ("/openapi.json", "/swagger.json"):
                            try:
                                spec = resp.json()
                                openapi_spec = spec
                                entry["openapi_title"] = spec.get("info", {}).get("title", "")
                                entry["openapi_version"] = spec.get("info", {}).get("version", "")
                                paths = list(spec.get("paths", {}).keys())[:20]
                                entry["endpoints"] = paths
                            except (json.JSONDecodeError, ValueError):
                                pass
                        found.append(entry)
                except httpx.RequestError:
                    continue
    except httpx.RequestError as exc:
        return {"error": f"Cannot reach {base}: {exc}"}

    result: dict[str, Any] = {
        "base_url": base,
        "discovered_endpoints": found,
    }
    if openapi_spec:
        result["has_openapi_spec"] = True
        result["openapi_paths_count"] = len(openapi_spec.get("paths", {}))
    else:
        result["has_openapi_spec"] = False

    return result


# ---------------------------------------------------------------------------
# Tool 8: generate_assertions
# ---------------------------------------------------------------------------


@mcp.tool()
def generate_assertions(
    response_status: int,
    response_body: str,
    response_headers: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Suggest test assertions for an API response. Returns a list of assertion objects that can be added to a request.

    Args:
        response_status: HTTP status code of the response
        response_body: Response body text
        response_headers: Optional response headers
    """
    assertions: list[dict[str, str]] = []
    assertions.append({
        "type": "status",
        "expected": str(response_status),
        "path": "",
        "operator": "eq",
    })

    if response_body.strip().startswith("{"):
        try:
            data = json.loads(response_body)
            for key in list(data.keys())[:5]:
                assertions.append({
                    "type": "json_path",
                    "path": key,
                    "expected": "",
                    "operator": "exists",
                })
        except (json.JSONDecodeError, ValueError, AttributeError):
            pass
    elif response_body.strip().startswith("["):
        try:
            data = json.loads(response_body)
            if isinstance(data, list) and len(data) > 0:
                assertions.append({
                    "type": "json_path",
                    "path": "0",
                    "expected": "",
                    "operator": "exists",
                })
        except (json.JSONDecodeError, ValueError):
            pass

    if response_headers:
        if "content-type" in {k.lower() for k in response_headers}:
            assertions.append({
                "type": "header_exists",
                "path": "content-type",
                "expected": "",
                "operator": "eq",
            })

    return assertions


# ---------------------------------------------------------------------------
# Tool 9: heal_assertion
# ---------------------------------------------------------------------------


@mcp.tool()
def heal_assertion(
    assertion_type: str,
    assertion_path: str,
    assertion_expected: str,
    response_body: str,
) -> dict[str, Any]:
    """When an assertion fails, suggest a fix based on the actual response. Uses fuzzy matching to find renamed/moved fields.

    Args:
        assertion_type: Type of the failed assertion (e.g. "json_path")
        assertion_path: The path that failed (e.g. "user.username")
        assertion_expected: The expected value
        response_body: The actual response body
    """
    from .assertions import Assertion
    from .healing import heal

    assertion = Assertion(
        type=assertion_type,  # type: ignore[arg-type]
        path=assertion_path,
        expected=assertion_expected,
        operator="eq",
    )
    output = heal(assertion, response_body)
    return {
        "candidates": [
            {
                "path": c.suggested_path,
                "confidence": c.confidence,
                "reason": c.reason,
            }
            for c in output.candidates
        ],
        "auto_fixable": output.auto_fixable,
    }


# ---------------------------------------------------------------------------
# Tool 10: compare_responses
# ---------------------------------------------------------------------------


@mcp.tool()
def compare_responses(response_a: str, response_b: str) -> dict[str, Any]:
    """Compare two API response bodies and return the differences. Useful for regression testing.

    Args:
        response_a: First response body (JSON string)
        response_b: Second response body (JSON string)
    """
    try:
        a = json.loads(response_a)
        b = json.loads(response_b)
    except (json.JSONDecodeError, ValueError) as exc:
        return {"error": f"Invalid JSON: {exc}"}

    diffs = _deep_diff(a, b, "")
    return {
        "identical": len(diffs) == 0,
        "diff_count": len(diffs),
        "diffs": diffs[:50],  # Cap at 50 to avoid huge payloads.
    }


def _deep_diff(a: Any, b: Any, path: str) -> list[dict[str, Any]]:
    """Recursive deep-diff of two JSON-like structures."""
    diffs: list[dict[str, Any]] = []
    if type(a) is not type(b):
        diffs.append({
            "path": path or "$",
            "type": "type_changed",
            "a": str(type(a).__name__),
            "b": str(type(b).__name__),
        })
        return diffs

    if isinstance(a, dict):
        all_keys = set(a.keys()) | set(b.keys())
        for key in sorted(all_keys):
            child_path = f"{path}.{key}" if path else key
            if key not in a:
                diffs.append({"path": child_path, "type": "added", "value": b[key]})
            elif key not in b:
                diffs.append({"path": child_path, "type": "removed", "value": a[key]})
            else:
                diffs.extend(_deep_diff(a[key], b[key], child_path))
    elif isinstance(a, list):
        max_len = max(len(a), len(b))
        for i in range(max_len):
            child_path = f"{path}[{i}]" if path else f"[{i}]"
            if i >= len(a):
                diffs.append({"path": child_path, "type": "added", "value": b[i]})
            elif i >= len(b):
                diffs.append({"path": child_path, "type": "removed", "value": a[i]})
            else:
                diffs.extend(_deep_diff(a[i], b[i], child_path))
    elif a != b:
        diffs.append({
            "path": path or "$",
            "type": "value_changed",
            "a": a,
            "b": b,
        })
    return diffs


# ---------------------------------------------------------------------------
# Resource: collection list
# ---------------------------------------------------------------------------


@mcp.resource("collections://list")
def collections_resource() -> str:
    """List of all API collections in Theridion."""
    from . import storage

    summaries = storage.list_summaries()
    lines = [
        f"- {s.name} ({s.request_count} requests) [id: {s.id}]"
        for s in summaries
    ]
    return "\n".join(lines) if lines else "No collections saved yet."


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


@mcp.prompt()
def test_api(base_url: str) -> str:
    """Generate a prompt for testing an API endpoint."""
    return f"""Please help me test the API at {base_url}.

1. First, use inspect_api to discover available endpoints
2. Then, use execute_request to test each endpoint
3. For each response, use generate_assertions to create test assertions
4. If any assertions fail, use heal_assertion to suggest fixes
5. Save all tested requests to a new collection"""


@mcp.prompt()
def debug_request(method: str, url: str, error: str) -> str:
    """Generate a prompt for debugging a failing API request."""
    return f"""I'm having trouble with this API request:

Method: {method}
URL: {url}
Error: {error}

Please help me debug this by:
1. Execute the request and inspect the response
2. Check the response headers for clues
3. Suggest fixes based on the error"""
