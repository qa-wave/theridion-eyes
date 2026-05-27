"""Universal import: parse collections from HAR, Hoppscotch, Thunder Client,
OpenAPI/Swagger, SoapUI XML, Bruno .bru, HTTPie, and Paw/RapidAPI.

Delegates Postman and Insomnia to the existing importer when auto-detected.
"""

from __future__ import annotations

import json
import re
import uuid
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage
from ..models import Collection, CollectionItem

router = APIRouter(prefix="/api/import/universal", tags=["universal-import"])

VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------

class UniversalImportInput(BaseModel):
    content: str = Field(..., min_length=1)
    filename: str | None = None
    format: str = "auto"


class UniversalImportOutput(BaseModel):
    format_detected: str
    collection_id: str
    collection_name: str
    request_count: int
    warnings: list[str]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("", response_model=UniversalImportOutput)
def universal_import(body: UniversalImportInput) -> UniversalImportOutput:
    fmt = body.format
    raw = body.content
    filename = body.filename or ""

    if fmt == "auto":
        fmt = _auto_detect(raw, filename)

    parsers: dict[str, Any] = {
        "har": _parse_har,
        "hoppscotch": _parse_hoppscotch,
        "thunder": _parse_thunder,
        "openapi": _parse_openapi,
        "soapui": _parse_soapui,
        "bruno": _parse_bruno,
        "httpie": _parse_httpie,
        "paw": _parse_paw,
        "postman": _delegate_postman,
        "insomnia": _delegate_insomnia,
        "curl": _parse_curl_fallback,
    }

    parser = parsers.get(fmt)
    if parser is None:
        raise HTTPException(status_code=400, detail=f"Unknown or undetectable format: {fmt}")

    coll, warnings = parser(raw, filename)
    storage._atomic_write(coll)
    count = _count_requests(coll.items)

    return UniversalImportOutput(
        format_detected=fmt,
        collection_id=coll.id,
        collection_name=coll.name,
        request_count=count,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------

def _auto_detect(raw: str, filename: str) -> str:
    stripped = raw.strip()

    # 1. Try JSON
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            pass
        else:
            return _detect_json_format(data)

    # 2. Try XML (SoapUI)
    if stripped.startswith("<?xml") or stripped.startswith("<"):
        try:
            ET.fromstring(stripped)
            if "soapui-project" in stripped[:500].lower():
                return "soapui"
        except ET.ParseError:
            pass

    # 3. Bruno .bru patterns
    if _looks_like_bruno(stripped):
        return "bruno"

    # 4. Paw (SQLite magic bytes or .paw extension)
    if filename.endswith(".paw") or stripped.startswith("SQLite format"):
        return "paw"

    # 5. Fallback: try as cURL
    if stripped.lower().startswith("curl "):
        return "curl"

    raise HTTPException(
        status_code=400,
        detail="Could not auto-detect format. Specify format explicitly.",
    )


def _detect_json_format(data: Any) -> str:
    if not isinstance(data, dict):
        # Could be a list — some HAR variants?
        return "postman"  # fallback

    # HAR
    if "log" in data and isinstance(data["log"], dict):
        if "entries" in data["log"]:
            return "har"

    # Postman v2.x
    info = data.get("info")
    if isinstance(info, dict):
        schema = info.get("schema", "")
        if isinstance(schema, str) and "v2" in schema:
            return "postman"

    # Insomnia
    if data.get("_type") == "export":
        return "insomnia"
    if "resources" in data and isinstance(data["resources"], list):
        for r in data["resources"]:
            if isinstance(r, dict) and "_type" in r:
                return "insomnia"

    # Thunder Client
    if data.get("client") == "Thunder Client":
        return "thunder"

    # OpenAPI / Swagger
    if "openapi" in data or "swagger" in data:
        return "openapi"

    # Hoppscotch (has name + folders, no info key)
    if "name" in data and "folders" in data and "info" not in data:
        return "hoppscotch"

    # HTTPie
    meta = data.get("__meta__")
    if isinstance(meta, dict) and "httpie" in str(meta).lower():
        return "httpie"

    # Default to postman
    return "postman"


def _looks_like_bruno(raw: str) -> bool:
    lines = raw.split("\n", 20)
    patterns = ("meta {", "get {", "post {", "put {", "patch {",
                "delete {", "head {", "options {", "headers {")
    hits = sum(1 for line in lines if any(line.strip().startswith(p) for p in patterns))
    return hits >= 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_method(m: str) -> str:
    m = m.upper()
    return m if m in VALID_METHODS else "GET"


def _count_requests(items: list[CollectionItem]) -> int:
    count = 0
    for it in items:
        if it.is_folder:
            count += _count_requests(it.items)
        else:
            count += 1
    return count


def _name_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        return path.split("/")[-1] if path else parsed.hostname or url[:60]
    except Exception:
        return url[:60] or "Untitled"


# ---------------------------------------------------------------------------
# HAR parser
# ---------------------------------------------------------------------------

def _parse_har(raw: str, _filename: str) -> tuple[Collection, list[str]]:
    data = json.loads(raw)
    entries = data.get("log", {}).get("entries", [])
    warnings: list[str] = []
    items: list[CollectionItem] = []

    for entry in entries:
        req = entry.get("request", {})
        url = req.get("url", "")
        method = _safe_method(req.get("method", "GET"))
        headers: dict[str, str] = {}
        for h in req.get("headers", []):
            name = h.get("name", "")
            # Skip pseudo-headers and cookie headers
            if name.startswith(":") or name.lower() in ("cookie", "host"):
                continue
            headers[name] = h.get("value", "")

        body: str | None = None
        post_data = req.get("postData")
        if isinstance(post_data, dict):
            body = post_data.get("text")

        items.append(CollectionItem(
            id=str(uuid.uuid4()),
            name=_name_from_url(url),
            method=method,
            url=url,
            headers=headers,
            body=body,
        ))

    if not items:
        warnings.append("No entries found in HAR log")

    coll = Collection(
        id=str(uuid.uuid4()),
        name="Imported (HAR)",
        version=1,
        items=items,
    )
    return coll, warnings


# ---------------------------------------------------------------------------
# Hoppscotch parser
# ---------------------------------------------------------------------------

def _parse_hoppscotch(raw: str, _filename: str) -> tuple[Collection, list[str]]:
    data = json.loads(raw)
    warnings: list[str] = []
    name = data.get("name", "Imported (Hoppscotch)")
    items = _convert_hoppscotch_items(data, warnings)

    coll = Collection(
        id=str(uuid.uuid4()),
        name=name,
        version=1,
        items=items,
    )
    return coll, warnings


def _convert_hoppscotch_items(
    data: dict[str, Any], warnings: list[str],
) -> list[CollectionItem]:
    items: list[CollectionItem] = []

    # Requests at this level
    for req in data.get("requests", []):
        headers: dict[str, str] = {}
        for h in req.get("headers", []):
            if isinstance(h, dict) and h.get("active", True):
                headers[h.get("key", "")] = h.get("value", "")

        body: str | None = None
        body_data = req.get("body", {})
        if isinstance(body_data, dict):
            body = body_data.get("body") or body_data.get("contentType")
        elif isinstance(body_data, str):
            body = body_data

        items.append(CollectionItem(
            id=str(uuid.uuid4()),
            name=req.get("name", "Untitled"),
            method=_safe_method(req.get("method", "GET")),
            url=req.get("endpoint", req.get("url", "")),
            headers=headers,
            body=body,
        ))

    # Folders
    for folder in data.get("folders", []):
        child_items = _convert_hoppscotch_items(folder, warnings)
        items.append(CollectionItem(
            id=str(uuid.uuid4()),
            name=folder.get("name", "Folder"),
            is_folder=True,
            items=child_items,
        ))

    return items


# ---------------------------------------------------------------------------
# Thunder Client parser
# ---------------------------------------------------------------------------

def _parse_thunder(raw: str, _filename: str) -> tuple[Collection, list[str]]:
    data = json.loads(raw)
    warnings: list[str] = []
    requests = data.get("requests", data.get("collections", []))

    # Thunder Client can export as a flat list or nested
    if isinstance(requests, list):
        items = _convert_thunder_requests(requests, warnings)
    else:
        items = []
        warnings.append("Unexpected Thunder Client structure")

    coll = Collection(
        id=str(uuid.uuid4()),
        name=data.get("collectionName", data.get("name", "Imported (Thunder Client)")),
        version=1,
        items=items,
    )
    return coll, warnings


def _convert_thunder_requests(
    requests: list[dict[str, Any]], warnings: list[str],
) -> list[CollectionItem]:
    items: list[CollectionItem] = []
    for req in requests:
        headers: dict[str, str] = {}
        for h in req.get("headers", []):
            if isinstance(h, dict):
                headers[h.get("name", h.get("key", ""))] = h.get("value", "")

        body: str | None = None
        body_data = req.get("body")
        if isinstance(body_data, dict):
            body = body_data.get("raw") or body_data.get("body")
        elif isinstance(body_data, str):
            body = body_data

        url = req.get("url", "")
        # Append query params
        params = req.get("params", [])
        if params and isinstance(params, list):
            qs = "&".join(
                f"{p.get('name', p.get('key', ''))}={p.get('value', '')}"
                for p in params
                if isinstance(p, dict) and not p.get("isDisabled", False)
            )
            if qs:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}{qs}"

        items.append(CollectionItem(
            id=str(uuid.uuid4()),
            name=req.get("name", _name_from_url(url)),
            method=_safe_method(req.get("method", "GET")),
            url=url,
            headers=headers,
            body=body,
        ))
    return items


# ---------------------------------------------------------------------------
# OpenAPI / Swagger parser
# ---------------------------------------------------------------------------

def _parse_openapi(raw: str, _filename: str) -> tuple[Collection, list[str]]:
    data = json.loads(raw)
    warnings: list[str] = []

    # Title
    info = data.get("info", {})
    title = info.get("title", "Imported (OpenAPI)")

    # Base URL
    base_url = ""
    if "servers" in data and data["servers"]:
        base_url = data["servers"][0].get("url", "")
    elif "host" in data:
        # Swagger 2.0
        scheme = "https"
        schemes = data.get("schemes", [])
        if schemes:
            scheme = schemes[0]
        base_path = data.get("basePath", "")
        base_url = f"{scheme}://{data['host']}{base_path}"

    paths = data.get("paths", {})
    items: list[CollectionItem] = []

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method_lower, operation in path_item.items():
            if method_lower.upper() not in VALID_METHODS:
                continue
            if not isinstance(operation, dict):
                continue

            op_id = operation.get("operationId", "")
            summary = operation.get("summary", "")
            name = op_id or summary or f"{method_lower.upper()} {path}"

            full_url = f"{base_url}{path}" if base_url else path

            # Try to extract request body content type header
            headers: dict[str, str] = {}
            consumes = operation.get("consumes", data.get("consumes", []))
            if consumes and isinstance(consumes, list):
                headers["Content-Type"] = consumes[0]

            items.append(CollectionItem(
                id=str(uuid.uuid4()),
                name=name,
                method=_safe_method(method_lower),
                url=full_url,
                headers=headers,
            ))

    if not items:
        warnings.append("No paths found in OpenAPI spec")

    coll = Collection(
        id=str(uuid.uuid4()),
        name=title,
        version=1,
        items=items,
    )
    return coll, warnings


# ---------------------------------------------------------------------------
# SoapUI XML parser
# ---------------------------------------------------------------------------

def _parse_soapui(raw: str, _filename: str) -> tuple[Collection, list[str]]:
    warnings: list[str] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"Invalid XML: {e}") from e

    # SoapUI uses namespaces; strip them for easier traversal
    ns_pattern = re.compile(r"\{[^}]+\}")

    def strip_ns(tag: str) -> str:
        return ns_pattern.sub("", tag)

    project_name = root.attrib.get("name", "Imported (SoapUI)")
    items: list[CollectionItem] = []

    # Walk the tree looking for test steps with requests, or top-level interfaces
    for elem in root.iter():
        tag = strip_ns(elem.tag)

        # Interface → operation → request pattern
        if tag == "request":
            endpoint = elem.attrib.get("endpoint", "")
            name = elem.attrib.get("name", "")
            method_attr = elem.attrib.get("method", "POST")
            body_elem = elem.find(".//{*}request") if elem.find(".//{*}request") is not None else None

            # Try to get body text from the request element itself
            request_text: str | None = None
            for child in elem:
                child_tag = strip_ns(child.tag)
                if child_tag == "request":
                    request_text = child.text

            if not endpoint and not name:
                continue

            items.append(CollectionItem(
                id=str(uuid.uuid4()),
                name=name or _name_from_url(endpoint),
                method=_safe_method(method_attr),
                url=endpoint,
                body=request_text,
            ))

        # restMethod pattern (REST projects)
        elif tag == "restMethod":
            method_str = elem.attrib.get("method", "GET")
            name = elem.attrib.get("name", "")
            # Find parent restResource for path
            items.append(CollectionItem(
                id=str(uuid.uuid4()),
                name=name or "Untitled",
                method=_safe_method(method_str),
                url="",  # SoapUI REST resources need full resolution
            ))

    if not items:
        warnings.append("No requests found in SoapUI project — the XML structure may differ from expected")

    # Group into folders by test suite if we find that structure
    test_suites: dict[str, list[CollectionItem]] = {}
    for elem in root.iter():
        tag = strip_ns(elem.tag)
        if tag == "testSuite":
            suite_name = elem.attrib.get("name", "Test Suite")
            suite_items: list[CollectionItem] = []
            for step in elem.iter():
                step_tag = strip_ns(step.tag)
                if step_tag == "restRequest" or step_tag == "request":
                    endpoint = step.attrib.get("endpoint", "")
                    step_name = step.attrib.get("name", _name_from_url(endpoint))
                    method_str = step.attrib.get("method", "POST")
                    body_text: str | None = None
                    for child in step:
                        if strip_ns(child.tag) == "request":
                            body_text = child.text
                    suite_items.append(CollectionItem(
                        id=str(uuid.uuid4()),
                        name=step_name,
                        method=_safe_method(method_str),
                        url=endpoint,
                        body=body_text,
                    ))
            if suite_items:
                test_suites[suite_name] = suite_items

    # If we found test suites, use those as folder hierarchy instead
    if test_suites:
        items = []
        for suite_name, suite_items in test_suites.items():
            items.append(CollectionItem(
                id=str(uuid.uuid4()),
                name=suite_name,
                is_folder=True,
                items=suite_items,
            ))

    coll = Collection(
        id=str(uuid.uuid4()),
        name=project_name,
        version=1,
        items=items,
    )
    return coll, warnings


# ---------------------------------------------------------------------------
# Bruno .bru parser
# ---------------------------------------------------------------------------

def _parse_bruno(raw: str, _filename: str) -> tuple[Collection, list[str]]:
    warnings: list[str] = []

    name = "Imported (Bruno)"
    method = "GET"
    url = ""
    headers: dict[str, str] = {}
    body: str | None = None

    current_block: str | None = None
    body_lines: list[str] = []

    for line in raw.split("\n"):
        stripped = line.strip()

        # Block opening
        block_match = re.match(r"^(\w[\w:]*)\s*\{", stripped)
        if block_match and not stripped.endswith("}"):
            current_block = block_match.group(1).lower()
            body_lines = []
            continue

        # Block closing
        if stripped == "}" and current_block:
            if current_block in ("body", "body:json", "body:xml", "body:text"):
                body = "\n".join(body_lines).strip() or None
            current_block = None
            continue

        if current_block is None:
            continue

        # Parse block contents
        if current_block == "meta":
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if key == "name":
                    name = val

        elif current_block in ("get", "post", "put", "patch", "delete", "head", "options"):
            method = current_block.upper()
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                if key.strip() == "url":
                    url = val.strip()
            elif stripped and not stripped.startswith("#"):
                # Some .bru files have just the URL on a line
                if stripped.startswith("http") or stripped.startswith("{{"):
                    url = stripped

        elif current_block == "headers":
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if key and not key.startswith("#") and not key.startswith("~"):
                    headers[key] = val

        elif current_block in ("body", "body:json", "body:xml", "body:text"):
            body_lines.append(line)

    items = [CollectionItem(
        id=str(uuid.uuid4()),
        name=name,
        method=_safe_method(method),
        url=url,
        headers=headers,
        body=body,
    )]

    coll = Collection(
        id=str(uuid.uuid4()),
        name=name,
        version=1,
        items=items,
    )
    return coll, warnings


# ---------------------------------------------------------------------------
# HTTPie parser
# ---------------------------------------------------------------------------

def _parse_httpie(raw: str, _filename: str) -> tuple[Collection, list[str]]:
    data = json.loads(raw)
    warnings: list[str] = []

    headers: dict[str, str] = {}
    raw_headers = data.get("headers", {})
    if isinstance(raw_headers, dict):
        for k, v in raw_headers.items():
            if isinstance(v, str):
                headers[k] = v
            elif isinstance(v, list) and v:
                headers[k] = v[0]

    # HTTPie session files don't have full request info, mainly headers/cookies
    warnings.append("HTTPie session files contain headers and cookies but not full request definitions")

    items = [CollectionItem(
        id=str(uuid.uuid4()),
        name="HTTPie session",
        method="GET",
        url="",
        headers=headers,
    )]

    coll = Collection(
        id=str(uuid.uuid4()),
        name="Imported (HTTPie)",
        version=1,
        items=items,
    )
    return coll, warnings


# ---------------------------------------------------------------------------
# Paw/RapidAPI — error only
# ---------------------------------------------------------------------------

def _parse_paw(_raw: str, _filename: str) -> tuple[Collection, list[str]]:
    raise HTTPException(
        status_code=400,
        detail="Paw files (.paw) are SQLite databases. Export as cURL or HAR from Paw first.",
    )


# ---------------------------------------------------------------------------
# Delegation to existing importer
# ---------------------------------------------------------------------------

def _delegate_postman(raw: str, _filename: str) -> tuple[Collection, list[str]]:
    from .importer import _import_postman
    data = json.loads(raw)
    coll = _import_postman(data)
    return coll, []


def _delegate_insomnia(raw: str, _filename: str) -> tuple[Collection, list[str]]:
    from .importer import _import_insomnia
    data = json.loads(raw)
    coll = _import_insomnia(data)
    return coll, []


# ---------------------------------------------------------------------------
# cURL fallback
# ---------------------------------------------------------------------------

def _parse_curl_fallback(raw: str, _filename: str) -> tuple[Collection, list[str]]:
    warnings: list[str] = []
    stripped = raw.strip()

    # Very basic cURL parsing
    method = "GET"
    url = ""
    headers: dict[str, str] = {}
    body: str | None = None

    parts = stripped.split()
    i = 0
    while i < len(parts):
        part = parts[i]
        if part.lower() == "curl":
            i += 1
            continue
        if part in ("-X", "--request") and i + 1 < len(parts):
            method = parts[i + 1].strip("'\"")
            i += 2
            continue
        if part in ("-H", "--header") and i + 1 < len(parts):
            hdr = parts[i + 1].strip("'\"")
            if ":" in hdr:
                k, _, v = hdr.partition(":")
                headers[k.strip()] = v.strip()
            i += 2
            continue
        if part in ("-d", "--data", "--data-raw") and i + 1 < len(parts):
            body = parts[i + 1].strip("'\"")
            if method == "GET":
                method = "POST"
            i += 2
            continue
        # URL (doesn't start with -)
        if not part.startswith("-") and (part.startswith("http") or part.startswith("'")):
            url = part.strip("'\"")
            i += 1
            continue
        i += 1

    if not url:
        warnings.append("Could not extract URL from cURL command")

    items = [CollectionItem(
        id=str(uuid.uuid4()),
        name=_name_from_url(url) if url else "cURL import",
        method=_safe_method(method),
        url=url,
        headers=headers,
        body=body,
    )]

    coll = Collection(
        id=str(uuid.uuid4()),
        name="Imported (cURL)",
        version=1,
        items=items,
    )
    return coll, warnings
