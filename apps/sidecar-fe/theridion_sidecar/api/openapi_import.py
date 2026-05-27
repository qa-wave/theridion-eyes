"""Enhanced OpenAPI/Swagger import with folder organization, auth, and example bodies.

Endpoints:
  POST /api/import/openapi          — parse + save as collection
  POST /api/import/openapi/preview  — parse only, return structure without saving
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import httpx
import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage
from ..models import AuthConfig, Collection, CollectionItem

router = APIRouter(prefix="/api/import/openapi", tags=["import-openapi"])

HTTP_METHODS: set[str] = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
JSON_MEDIA_TYPES = ("application/json", "application/problem+json", "*/*")


# --- Request / Response models ------------------------------------------------


class OpenApiImportInput(BaseModel):
    source: str = Field(..., min_length=1)
    collection_name: str | None = None
    base_url_override: str | None = None
    include_paths: list[str] | None = None
    exclude_paths: list[str] | None = None


class PreviewFolder(BaseModel):
    name: str
    request_count: int
    requests: list[dict[str, Any]] = Field(default_factory=list)


class PreviewOutput(BaseModel):
    title: str
    version: str
    base_url: str
    folder_count: int
    request_count: int
    folders: list[PreviewFolder] = Field(default_factory=list)
    auth_detected: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ImportOutput(BaseModel):
    collection_id: str
    collection_name: str
    request_count: int
    folder_count: int
    warnings: list[str] = Field(default_factory=list)


# --- Internal helpers ---------------------------------------------------------


def _fetch_source(source: str) -> str:
    """Return spec content from a URL or treat *source* as raw content."""
    stripped = source.strip()
    if stripped.startswith(("http://", "https://")):
        try:
            r = httpx.get(stripped, timeout=30, follow_redirects=True)
            r.raise_for_status()
            return r.text
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}") from exc
    return source


def _parse_spec(raw: str) -> dict[str, Any]:
    """Parse JSON or YAML into a dict."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise HTTPException(status_code=400, detail=f"Cannot parse as JSON or YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Spec root must be a JSON/YAML object")
    if "openapi" not in data and "swagger" not in data:
        raise HTTPException(status_code=400, detail="Not an OpenAPI/Swagger document (missing 'openapi' or 'swagger' key)")
    return data


def _resolve_ref(doc: dict[str, Any], node: Any, depth: int = 0) -> Any:
    if depth > 30:
        return node
    if not isinstance(node, dict) or "$ref" not in node:
        return node
    ref = node.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return node
    current: Any = doc
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return node
    return _resolve_ref(doc, current, depth + 1)


def _base_url_v2(doc: dict[str, Any]) -> str:
    """Extract base URL from Swagger 2.0 fields."""
    host = doc.get("host", "")
    base_path = doc.get("basePath", "")
    schemes = doc.get("schemes", ["https"])
    scheme = schemes[0] if isinstance(schemes, list) and schemes else "https"
    if host:
        return f"{scheme}://{host}{base_path}".rstrip("/")
    return base_path.rstrip("/")


def _base_url_v3(doc: dict[str, Any]) -> str:
    """Extract base URL from OpenAPI 3.x servers."""
    servers = doc.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict) and isinstance(first.get("url"), str):
            url = str(first["url"])
            # Substitute server variables with default values
            variables = first.get("variables")
            if isinstance(variables, dict):
                for var_name, var_def in variables.items():
                    if isinstance(var_def, dict):
                        default = var_def.get("default", "")
                        url = url.replace(f"{{{var_name}}}", str(default))
            return url.rstrip("/")
    return ""


def _base_url(doc: dict[str, Any], override: str | None) -> str:
    if override:
        return override.rstrip("/")
    if "swagger" in doc:
        return _base_url_v2(doc)
    return _base_url_v3(doc)


def _sample_for_schema(doc: dict[str, Any], schema: Any, depth: int = 0) -> Any:
    """Generate a sample value from a JSON Schema node."""
    if depth > 15:
        return None
    schema = _resolve_ref(doc, schema)
    if not isinstance(schema, dict):
        return None
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]

    # allOf — merge properties
    if "allOf" in schema and isinstance(schema["allOf"], list):
        merged: dict[str, Any] = {}
        for sub in schema["allOf"]:
            sub = _resolve_ref(doc, sub)
            if isinstance(sub, dict):
                sample = _sample_for_schema(doc, sub, depth + 1)
                if isinstance(sample, dict):
                    merged.update(sample)
        return merged if merged else None

    # oneOf / anyOf — use first
    for key in ("oneOf", "anyOf"):
        if key in schema and isinstance(schema[key], list) and schema[key]:
            return _sample_for_schema(doc, schema[key][0], depth + 1)

    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        props = schema.get("properties")
        if not isinstance(props, dict):
            return {}
        return {str(k): _sample_for_schema(doc, v, depth + 1) for k, v in props.items()}
    if schema_type == "array":
        item_sample = _sample_for_schema(doc, schema.get("items", {}), depth + 1)
        return [item_sample] if item_sample is not None else []
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0.0
    if schema_type == "boolean":
        return True
    if schema_type == "string":
        fmt = schema.get("format", "")
        if fmt == "date":
            return "2024-01-01"
        if fmt == "date-time":
            return "2024-01-01T00:00:00Z"
        if fmt == "email":
            return "user@example.com"
        if fmt == "uri" or fmt == "url":
            return "https://example.com"
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        return "string"
    return None


def _media_object(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, dict):
        return None
    for media_type in JSON_MEDIA_TYPES:
        media = content.get(media_type)
        if isinstance(media, dict):
            return media
    for media in content.values():
        if isinstance(media, dict):
            return media
    return None


def _request_body_v3(doc: dict[str, Any], operation: dict[str, Any]) -> str | None:
    """Extract example request body from OpenAPI 3.x requestBody."""
    request_body = _resolve_ref(doc, operation.get("requestBody"))
    if not isinstance(request_body, dict):
        return None
    media = _media_object(request_body.get("content"))
    if not media:
        return None
    if "example" in media:
        return json.dumps(media["example"], indent=2)
    examples = media.get("examples")
    if isinstance(examples, dict) and examples:
        first = next(iter(examples.values()))
        first = _resolve_ref(doc, first)
        if isinstance(first, dict) and "value" in first:
            return json.dumps(first["value"], indent=2)
    schema = media.get("schema")
    sample = _sample_for_schema(doc, schema)
    return json.dumps(sample, indent=2) if sample is not None else None


def _request_body_v2(doc: dict[str, Any], operation: dict[str, Any]) -> str | None:
    """Extract example request body from Swagger 2.0 body parameter."""
    params = operation.get("parameters")
    if not isinstance(params, list):
        return None
    for param in params:
        param = _resolve_ref(doc, param)
        if not isinstance(param, dict):
            continue
        if param.get("in") == "body":
            schema = _resolve_ref(doc, param.get("schema"))
            if schema:
                sample = _sample_for_schema(doc, schema)
                if sample is not None:
                    return json.dumps(sample, indent=2)
    return None


def _request_body(doc: dict[str, Any], operation: dict[str, Any], is_v2: bool) -> str | None:
    if is_v2:
        return _request_body_v2(doc, operation)
    return _request_body_v3(doc, operation)


def _convert_path_params(path: str) -> str:
    """Convert {param} to {{param}} for Theridion template syntax."""
    return re.sub(r"\{([^}/]+)\}", r"{{\1}}", path)


def _build_url(base_url: str, path: str, operation: dict[str, Any], is_v2: bool) -> str:
    url_path = _convert_path_params(path)
    query_parts: list[str] = []
    params = operation.get("parameters")
    if isinstance(params, list):
        for param in params:
            if isinstance(param, dict) and param.get("in") == "query":
                name = param.get("name", "")
                if name:
                    query_parts.append(f"{name}={{{{{name}}}}}")
    query = "&".join(query_parts)
    return f"{base_url}{url_path}{'?' + query if query else ''}"


def _detect_auth(doc: dict[str, Any]) -> tuple[AuthConfig | None, str | None]:
    """Detect the primary auth scheme from the spec-level security definitions."""
    # OpenAPI 3.x
    components = doc.get("components", {})
    security_schemes = components.get("securitySchemes", {}) if isinstance(components, dict) else {}

    # Swagger 2.0
    if not security_schemes:
        security_schemes = doc.get("securityDefinitions", {})

    if not isinstance(security_schemes, dict) or not security_schemes:
        return None, None

    for name, scheme in security_schemes.items():
        if not isinstance(scheme, dict):
            continue
        scheme_type = str(scheme.get("type", "")).lower()
        bearer_format = str(scheme.get("bearerFormat", "")).lower()
        scheme_name = str(scheme.get("scheme", "")).lower()
        in_loc = str(scheme.get("in", "")).lower()
        param_name = str(scheme.get("name", ""))

        if scheme_type == "http" and scheme_name == "bearer":
            return AuthConfig(type="bearer", token="{{auth_token}}"), f"Bearer ({name})"
        if scheme_type == "http" and scheme_name == "basic":
            return AuthConfig(type="basic", username="{{username}}", password="{{password}}"), f"Basic ({name})"
        if scheme_type == "apikey" or scheme_type == "apiKey":
            add_to: Any = "header" if in_loc != "query" else "query"
            return AuthConfig(
                type="apikey",
                key=param_name or "X-API-Key",
                value="{{api_key}}",
                add_to=add_to,
            ), f"API Key ({name})"
        if scheme_type == "oauth2":
            # Represent as Bearer since we don't have full OAuth2 flow here
            return AuthConfig(type="bearer", token="{{oauth_token}}"), f"OAuth2 ({name})"
        if bearer_format:
            return AuthConfig(type="bearer", token="{{auth_token}}"), f"Bearer ({name})"

    return None, None


def _operation_auth(doc: dict[str, Any], operation: dict[str, Any], default_auth: AuthConfig | None) -> AuthConfig | None:
    """Check if operation has its own security override; otherwise use default."""
    security = operation.get("security")
    if security is not None:
        if isinstance(security, list) and len(security) == 0:
            return None  # explicitly no auth
    return default_auth


def _headers_for_operation(
    doc: dict[str, Any],
    operation: dict[str, Any],
    is_v2: bool,
    has_body: bool,
) -> dict[str, str]:
    """Build headers from the spec — Content-Type from consumes/produces."""
    headers: dict[str, str] = {}
    if has_body:
        if is_v2:
            consumes = operation.get("consumes") or doc.get("consumes", [])
            ct = consumes[0] if isinstance(consumes, list) and consumes else "application/json"
        else:
            ct = "application/json"
        headers["Content-Type"] = ct
    # Add Accept from produces (v2) or first response content type (v3)
    if is_v2:
        produces = operation.get("produces") or doc.get("produces", [])
        if isinstance(produces, list) and produces:
            headers["Accept"] = produces[0]
    return headers


def _collect_operations(
    doc: dict[str, Any],
    base_url: str,
    include_paths: list[str] | None,
    exclude_paths: list[str] | None,
) -> tuple[list[tuple[str, str, str, dict[str, Any]]], list[str]]:
    """Return (operations, warnings).

    Each operation tuple: (tag, method, path, operation_dict).
    """
    paths = doc.get("paths")
    if not isinstance(paths, dict):
        raise HTTPException(status_code=400, detail="Spec has no 'paths' key")

    is_v2 = "swagger" in doc
    default_auth, auth_label = _detect_auth(doc)
    operations: list[tuple[str, str, str, dict[str, Any]]] = []
    warnings: list[str] = []

    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        if include_paths and not any(path.startswith(p) for p in include_paths):
            continue
        if exclude_paths and any(path.startswith(p) for p in exclude_paths):
            continue

        # Path-level parameters apply to all methods
        path_params = path_item.get("parameters", [])

        for method_str, operation in path_item.items():
            method = str(method_str).upper()
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            # Merge path-level parameters
            op_params = operation.get("parameters", [])
            if isinstance(path_params, list) and path_params:
                merged_params = list(path_params)
                op_param_names = {(p.get("name"), p.get("in")) for p in op_params if isinstance(p, dict)}
                for pp in path_params:
                    if isinstance(pp, dict) and (pp.get("name"), pp.get("in")) not in op_param_names:
                        pass  # already in merged_params from path_params copy
                merged_params = [p for p in path_params if isinstance(p, dict) and (p.get("name"), p.get("in")) not in op_param_names]
                merged_params.extend(op_params if isinstance(op_params, list) else [])
                operation = {**operation, "parameters": merged_params}

            tags = operation.get("tags", [])
            tag = tags[0] if isinstance(tags, list) and tags else _path_to_tag(path)

            operations.append((tag, method, path, operation))

    return operations, warnings


def _path_to_tag(path: str) -> str:
    """Derive a folder name from a path prefix when no tags are present."""
    parts = [p for p in path.strip("/").split("/") if p and not p.startswith("{")]
    return parts[0].title() if parts else "Default"


def _build_collection_items(
    doc: dict[str, Any],
    base_url: str,
    operations: list[tuple[str, str, str, dict[str, Any]]],
) -> tuple[list[CollectionItem], int, int]:
    """Build folder-organized CollectionItems.

    Returns (items, request_count, folder_count).
    """
    is_v2 = "swagger" in doc
    default_auth, _ = _detect_auth(doc)

    # Group by tag
    tag_groups: dict[str, list[CollectionItem]] = {}
    request_count = 0

    for tag, method, path, operation in operations:
        summary = operation.get("summary") or operation.get("operationId") or f"{method} {path}"
        body = _request_body(doc, operation, is_v2)
        headers = _headers_for_operation(doc, operation, is_v2, body is not None)
        auth = _operation_auth(doc, operation, default_auth)
        url = _build_url(base_url, path, operation, is_v2)

        item = CollectionItem(
            id=str(uuid.uuid4()),
            name=str(summary),
            method=method,  # type: ignore[arg-type]
            url=url,
            headers=headers,
            body=body,
            auth=auth,
        )
        tag_groups.setdefault(tag, []).append(item)
        request_count += 1

    # If only one tag with all items, skip folder wrapping
    if len(tag_groups) <= 1 and request_count <= 5:
        items = list(next(iter(tag_groups.values()), []))
        return items, request_count, 0

    items: list[CollectionItem] = []
    for tag_name, tag_items in sorted(tag_groups.items()):
        folder = CollectionItem(
            id=str(uuid.uuid4()),
            name=tag_name,
            is_folder=True,
            items=tag_items,
        )
        items.append(folder)

    return items, request_count, len(tag_groups)


def _build_preview(
    doc: dict[str, Any],
    base_url: str,
    operations: list[tuple[str, str, str, dict[str, Any]]],
    warnings: list[str],
) -> PreviewOutput:
    """Build a preview structure without saving."""
    info = doc.get("info") if isinstance(doc.get("info"), dict) else {}
    _, auth_label = _detect_auth(doc)

    # Group by tag for preview
    tag_groups: dict[str, list[dict[str, Any]]] = {}
    for tag, method, path, operation in operations:
        summary = operation.get("summary") or operation.get("operationId") or f"{method} {path}"
        tag_groups.setdefault(tag, []).append({
            "method": method,
            "path": path,
            "name": str(summary),
        })

    folders = [
        PreviewFolder(name=tag, request_count=len(reqs), requests=reqs)
        for tag, reqs in sorted(tag_groups.items())
    ]

    total_requests = sum(f.request_count for f in folders)
    return PreviewOutput(
        title=str(info.get("title", "Untitled API")),
        version=str(info.get("version", "")),
        base_url=base_url,
        folder_count=len(folders),
        request_count=total_requests,
        folders=folders,
        auth_detected=auth_label,
        warnings=warnings,
    )


# --- Endpoints ----------------------------------------------------------------


@router.post("/preview", response_model=PreviewOutput)
def preview_openapi(body: OpenApiImportInput) -> PreviewOutput:
    """Parse an OpenAPI spec and return the structure without saving."""
    raw = _fetch_source(body.source)
    doc = _parse_spec(raw)
    base_url = _base_url(doc, body.base_url_override)
    operations, warnings = _collect_operations(doc, base_url, body.include_paths, body.exclude_paths)
    if not operations:
        warnings.append("No operations found in spec")
    return _build_preview(doc, base_url, operations, warnings)


@router.post("", response_model=ImportOutput)
def import_openapi(body: OpenApiImportInput) -> ImportOutput:
    """Parse an OpenAPI spec and create a collection."""
    raw = _fetch_source(body.source)
    doc = _parse_spec(raw)
    base_url = _base_url(doc, body.base_url_override)
    operations, warnings = _collect_operations(doc, base_url, body.include_paths, body.exclude_paths)
    items, request_count, folder_count = _build_collection_items(doc, base_url, operations)

    info = doc.get("info") if isinstance(doc.get("info"), dict) else {}
    name = body.collection_name or str(info.get("title", "OpenAPI Import"))
    coll = Collection(id=str(uuid.uuid4()), name=name, version=1, items=items)
    storage._atomic_write(coll)

    return ImportOutput(
        collection_id=coll.id,
        collection_name=coll.name,
        request_count=request_count,
        folder_count=folder_count,
        warnings=warnings,
    )
