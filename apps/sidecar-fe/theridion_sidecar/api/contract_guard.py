"""Contract Guard — validate API responses against OpenAPI specs.

Endpoints:
- POST /api/contract/validate — single response vs spec
- POST /api/contract/validate-collection — run + validate all requests
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import environments, storage

router = APIRouter(prefix="/api/contract", tags=["contract"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ContractViolation(BaseModel):
    path: str
    expected: str
    actual: str
    message: str


class ValidateInput(BaseModel):
    response_body: str
    response_status: int
    response_headers: dict[str, str] = Field(default_factory=dict)
    openapi_spec: str  # JSON or YAML string
    path: str
    method: str


class ValidateOutput(BaseModel):
    valid: bool
    violations: list[ContractViolation] = Field(default_factory=list)


class ValidateCollectionInput(BaseModel):
    collection_id: str
    spec_content: str


class PerRequestValidation(BaseModel):
    request_name: str
    method: str
    url: str
    status: int | None = None
    valid: bool
    violations: list[ContractViolation] = Field(default_factory=list)
    error: str | None = None


class ValidateCollectionOutput(BaseModel):
    results: list[PerRequestValidation] = Field(default_factory=list)
    total: int = 0
    valid_count: int = 0
    invalid_count: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_spec(raw: str) -> dict[str, Any]:
    """Parse an OpenAPI spec from JSON or YAML string."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        import yaml  # type: ignore[import-untyped]
        return yaml.safe_load(raw)  # type: ignore[no-any-return]
    except Exception:
        pass
    raise ValueError("Cannot parse spec as JSON or YAML")


def _find_schema(
    spec: dict[str, Any],
    path: str,
    method: str,
    status: int,
) -> dict[str, Any] | None:
    """Locate the response schema in the spec for a given path+method+status."""
    paths = spec.get("paths", {})
    path_item = paths.get(path)
    if path_item is None:
        # Try matching with path parameters.
        for p, item in paths.items():
            normalized = p.replace("{", "").replace("}", "")
            if normalized == path.replace("{", "").replace("}", ""):
                path_item = item
                break
    if path_item is None:
        return None

    operation = path_item.get(method.lower())
    if operation is None:
        return None

    responses = operation.get("responses", {})
    resp = responses.get(str(status)) or responses.get("default")
    if resp is None:
        return None

    # OpenAPI 3.x
    content = resp.get("content", {})
    for mime, media_obj in content.items():
        if "json" in mime:
            schema = media_obj.get("schema")
            if schema:
                return _resolve_schema(schema, spec)
    # OpenAPI 2.x (Swagger)
    if "schema" in resp:
        return _resolve_schema(resp["schema"], spec)
    return None


def _resolve_schema(
    schema: dict[str, Any], spec: dict[str, Any],
) -> dict[str, Any]:
    """Resolve $ref pointers one level deep."""
    ref = schema.get("$ref")
    if ref and isinstance(ref, str):
        parts = ref.lstrip("#/").split("/")
        resolved: Any = spec
        for part in parts:
            if isinstance(resolved, dict):
                resolved = resolved.get(part, {})
        if isinstance(resolved, dict):
            return resolved
    return schema


def _validate_value(
    value: Any,
    schema: dict[str, Any],
    spec: dict[str, Any],
    path: str,
) -> list[ContractViolation]:
    """Recursively validate a value against a JSON Schema subset."""
    violations: list[ContractViolation] = []
    schema = _resolve_schema(schema, spec)
    expected_type = schema.get("type")

    if expected_type == "object":
        if not isinstance(value, dict):
            violations.append(ContractViolation(
                path=path, expected="object", actual=type(value).__name__,
                message=f"Expected object at {path}, got {type(value).__name__}",
            ))
            return violations
        props = schema.get("properties", {})
        required = schema.get("required", [])
        for req_key in required:
            if req_key not in value:
                violations.append(ContractViolation(
                    path=f"{path}.{req_key}", expected="present", actual="missing",
                    message=f"Required property '{req_key}' missing at {path}",
                ))
        for key, prop_schema in props.items():
            if key in value:
                violations.extend(
                    _validate_value(value[key], prop_schema, spec, f"{path}.{key}")
                )
    elif expected_type == "array":
        if not isinstance(value, list):
            violations.append(ContractViolation(
                path=path, expected="array", actual=type(value).__name__,
                message=f"Expected array at {path}, got {type(value).__name__}",
            ))
        elif schema.get("items") and value:
            violations.extend(
                _validate_value(value[0], schema["items"], spec, f"{path}[0]")
            )
    elif expected_type == "string":
        if not isinstance(value, str):
            violations.append(ContractViolation(
                path=path, expected="string", actual=type(value).__name__,
                message=f"Expected string at {path}, got {type(value).__name__}",
            ))
    elif expected_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            violations.append(ContractViolation(
                path=path, expected="integer", actual=type(value).__name__,
                message=f"Expected integer at {path}, got {type(value).__name__}",
            ))
    elif expected_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            violations.append(ContractViolation(
                path=path, expected="number", actual=type(value).__name__,
                message=f"Expected number at {path}, got {type(value).__name__}",
            ))
    elif expected_type == "boolean":
        if not isinstance(value, bool):
            violations.append(ContractViolation(
                path=path, expected="boolean", actual=type(value).__name__,
                message=f"Expected boolean at {path}, got {type(value).__name__}",
            ))

    return violations


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/validate", response_model=ValidateOutput)
async def validate_response(body: ValidateInput) -> ValidateOutput:
    try:
        spec = _parse_spec(body.openapi_spec)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    schema = _find_schema(spec, body.path, body.method, body.response_status)
    if schema is None:
        return ValidateOutput(
            valid=True,
            violations=[ContractViolation(
                path="/", expected="schema", actual="none",
                message="No schema found for this path/method/status in the spec",
            )],
        )

    try:
        response_data = json.loads(body.response_body)
    except json.JSONDecodeError:
        return ValidateOutput(
            valid=False,
            violations=[ContractViolation(
                path="/", expected="valid JSON", actual="parse error",
                message="Response body is not valid JSON",
            )],
        )

    violations = _validate_value(response_data, schema, spec, "$")
    return ValidateOutput(valid=len(violations) == 0, violations=violations)


@router.post("/validate-collection", response_model=ValidateCollectionOutput)
async def validate_collection(body: ValidateCollectionInput) -> ValidateCollectionOutput:
    coll = storage.get(body.collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")

    try:
        spec = _parse_spec(body.spec_content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    from .runner import _collect_requests

    requests = _collect_requests(coll.items)
    results: list[PerRequestValidation] = []

    for req in requests:
        if not req.url:
            results.append(PerRequestValidation(
                request_name=req.name, method=req.method or "GET",
                url="", valid=False, error="No URL specified",
            ))
            continue

        try:
            async with httpx.AsyncClient(http2=True, timeout=30) as client:
                response = await client.request(
                    method=req.method or "GET",
                    url=req.url,
                    headers=req.headers,
                    content=req.body.encode("utf-8") if req.body else None,
                )
            resp_body = response.text
            try:
                response_data = json.loads(resp_body)
            except json.JSONDecodeError:
                results.append(PerRequestValidation(
                    request_name=req.name, method=req.method or "GET",
                    url=req.url, status=response.status_code,
                    valid=False, error="Response body is not valid JSON",
                ))
                continue

            # Try to match URL path to spec paths.
            from urllib.parse import urlparse
            url_path = urlparse(req.url).path
            schema = _find_schema(spec, url_path, req.method or "GET", response.status_code)
            if schema is None:
                results.append(PerRequestValidation(
                    request_name=req.name, method=req.method or "GET",
                    url=req.url, status=response.status_code,
                    valid=True, violations=[],
                ))
                continue

            violations = _validate_value(response_data, schema, spec, "$")
            results.append(PerRequestValidation(
                request_name=req.name, method=req.method or "GET",
                url=req.url, status=response.status_code,
                valid=len(violations) == 0, violations=violations,
            ))
        except Exception as exc:
            results.append(PerRequestValidation(
                request_name=req.name, method=req.method or "GET",
                url=req.url, valid=False, error=str(exc),
            ))

    valid_count = sum(1 for r in results if r.valid)
    return ValidateCollectionOutput(
        results=results,
        total=len(results),
        valid_count=valid_count,
        invalid_count=len(results) - valid_count,
    )
