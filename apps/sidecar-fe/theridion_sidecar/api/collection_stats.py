"""Collection statistics endpoint.

Computes aggregate metrics about a collection's requests, test coverage,
auth usage, URL patterns, and health indicators.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from theridion_sidecar import storage
from theridion_sidecar.models import CollectionItem

router = APIRouter(prefix="/api/collections", tags=["collection-stats"])


def _walk_items(items: list[CollectionItem]):
    """Depth-first walk yielding (item, folder_path) pairs."""
    for item in items:
        yield item
        if item.is_folder:
            yield from _walk_items(item.items)


def _folder_breakdown(items: list[CollectionItem], prefix: str = "") -> list[dict[str, Any]]:
    """Build a flat list of folders with their request counts."""
    result: list[dict[str, Any]] = []
    for item in items:
        if item.is_folder:
            request_count = sum(1 for i in _walk_items(item.items) if not i.is_folder)
            path = f"{prefix}/{item.name}" if prefix else item.name
            result.append({"name": path, "request_count": request_count})
            result.extend(_folder_breakdown(item.items, path))
    return result


def _compute_stats(items: list[CollectionItem]) -> dict[str, Any]:
    """Compute comprehensive statistics for a collection's items tree."""
    requests: list[CollectionItem] = [
        it for it in _walk_items(items) if not it.is_folder
    ]
    total = len(requests)

    # Method breakdown
    method_counts: dict[str, int] = {}
    for r in requests:
        m = r.method or "GET"
        method_counts[m] = method_counts.get(m, 0) + 1

    # Folder breakdown
    folders = _folder_breakdown(items)

    # Assertion coverage
    with_assertions = sum(1 for r in requests if r.assertions)
    without_assertions = total - with_assertions

    assertion_type_dist: dict[str, int] = {}
    for r in requests:
        for a in r.assertions:
            assertion_type_dist[a.type] = assertion_type_dist.get(a.type, 0) + 1

    # Auth usage
    with_auth = sum(
        1 for r in requests if r.auth and r.auth.type != "none"
    )
    without_auth = total - with_auth

    auth_type_dist: dict[str, int] = {}
    for r in requests:
        if r.auth and r.auth.type != "none":
            auth_type_dist[r.auth.type] = auth_type_dist.get(r.auth.type, 0) + 1

    # URL analysis
    base_urls: set[str] = set()
    parameterized_urls = 0
    url_patterns: dict[str, int] = {}
    for r in requests:
        url = r.url or ""
        # Extract base URL (scheme + host)
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                base_urls.add(f"{parsed.scheme}://{parsed.netloc}")
        except Exception:
            pass
        # Check for parameterized URLs ({{var}} or :param or {param})
        if re.search(r"\{\{.*?\}\}|:\w+|\{[^}]+\}", url):
            parameterized_urls += 1
        # URL pattern (method + path without params)
        pattern_url = re.sub(r"\{\{.*?\}\}", "*", url)
        pattern_url = re.sub(r":\w+", "*", pattern_url)
        pattern_url = re.sub(r"\{[^}]+\}", "*", pattern_url)
        method = r.method or "GET"
        pattern_key = f"{method} {pattern_url}"
        url_patterns[pattern_key] = url_patterns.get(pattern_key, 0) + 1

    # Body analysis
    with_body = sum(1 for r in requests if r.body)
    without_body = total - with_body
    body_sizes = [len(r.body) for r in requests if r.body]
    avg_body_size = round(sum(body_sizes) / len(body_sizes)) if body_sizes else 0

    # Content types from headers
    content_types: dict[str, int] = {}
    for r in requests:
        for key, val in r.headers.items():
            if key.lower() == "content-type":
                content_types[val] = content_types.get(val, 0) + 1

    # Complexity metrics
    total_headers = sum(len(r.headers) for r in requests)
    total_variables_used = 0
    for r in requests:
        # Count {{var}} references in URL, headers, body
        url = r.url or ""
        total_variables_used += len(re.findall(r"\{\{.*?\}\}", url))
        for v in r.headers.values():
            total_variables_used += len(re.findall(r"\{\{.*?\}\}", v))
        if r.body:
            total_variables_used += len(re.findall(r"\{\{.*?\}\}", r.body))
    scripts_attached = sum(
        1 for r in requests
        if r.pre_request_script or r.post_response_script
    )

    return {
        "request_breakdown": {
            "total": total,
            "by_method": method_counts,
            "by_folder": folders,
        },
        "coverage": {
            "with_assertions": with_assertions,
            "without_assertions": without_assertions,
            "assertion_coverage_pct": round(
                (with_assertions / total * 100) if total > 0 else 0, 1
            ),
            "assertion_type_distribution": assertion_type_dist,
        },
        "auth_usage": {
            "with_auth": with_auth,
            "without_auth": without_auth,
            "auth_coverage_pct": round(
                (with_auth / total * 100) if total > 0 else 0, 1
            ),
            "auth_type_distribution": auth_type_dist,
        },
        "url_analysis": {
            "unique_base_urls": sorted(base_urls),
            "parameterized_urls": parameterized_urls,
            "url_patterns": url_patterns,
        },
        "body_analysis": {
            "with_body": with_body,
            "without_body": without_body,
            "content_types": content_types,
            "avg_body_size": avg_body_size,
        },
        "complexity": {
            "total_headers": total_headers,
            "total_variables_used": total_variables_used,
            "scripts_attached": scripts_attached,
        },
    }


@router.get("/{collection_id}/stats")
async def get_collection_stats(collection_id: str) -> dict[str, Any]:
    """Return comprehensive statistics for a collection."""
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    stats = _compute_stats(coll.items)
    stats["collection_id"] = coll.id
    stats["collection_name"] = coll.name
    return stats
