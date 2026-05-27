"""OpenAPI import/export and contract validation endpoints."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit

import yaml
from fastapi import APIRouter, HTTPException
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, Field

from ... import storage
from ...models import (
    Collection,
    CollectionItem,
    HttpMethod,
)

router = APIRouter()

HTTP_METHODS: set[str] = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
JSON_MEDIA_TYPES = ("application/json", "application/problem+json", "*/*")


class OpenApiImportInput(BaseModel):
    content: str = Field(..., min_length=1)
    format: Literal["auto", "json", "yaml"] = "auto"
    collection_name: str | None = None
    base_url: str | None = None


class OpenApiImportOutput(BaseModel):
    collection_id: str
    collection_name: str
    request_count: int


class OpenApiExportOutput(BaseModel):
    openapi: dict[str, Any]


class ContractValidateInput(BaseModel):
    openapi_content: str = Field(..., min_length=1)
    method: HttpMethod
    path: str
    status: int = 200
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""


class ContractViolation(BaseModel):
    path: str
    message: str


class ContractValidateOutput(BaseModel):
    passed: bool
    operation_id: str | None = None
    expected_statuses: list[str] = Field(default_factory=list)
    violations: list[ContractViolation] = Field(default_factory=list)


class ObservedResponse(BaseModel):
    method: HttpMethod
    path: str
    status: int
    body: str = ""
    headers: dict[str, str] = Field(default_factory=dict)


class ContractDriftInput(BaseModel):
    openapi_content: str = Field(..., min_length=1)
    collection_id: str | None = None
    observed: list[ObservedResponse] = Field(default_factory=list)


class ContractDriftOutput(BaseModel):
    missing_in_collection: list[str] = Field(default_factory=list)
    undocumented_requests: list[str] = Field(default_factory=list)
    failing_observations: list[ContractValidateOutput] = Field(default_factory=list)
    passed_observations: int = 0


def _parse_structured_content(content: str, fmt: str = "auto") -> dict[str, Any]:
    try:
        if fmt == "json":
            data = json.loads(content)
        elif fmt == "yaml":
            data = yaml.safe_load(content)
        else:
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = yaml.safe_load(content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid structured document: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="document root must be an object")
    return data


def _openapi_base_url(doc: dict[str, Any], override: str | None = None) -> str:
    if override:
        return override.rstrip("/")
    servers = doc.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict) and isinstance(first.get("url"), str):
            return str(first["url"]).rstrip("/")
    return ""


def _iter_openapi_operations(
    doc: dict[str, Any],
) -> list[tuple[str, str, dict[str, Any]]]:
    paths = doc.get("paths")
    if not isinstance(paths, dict):
        return []
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            upper = str(method).upper()
            if upper in HTTP_METHODS and isinstance(operation, dict):
                operations.append((upper, path, operation))
    return operations


def _operation_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def _resolve_ref(doc: dict[str, Any], node: Any) -> Any:
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
    return _resolve_ref(doc, current)


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


def _schema_for_response(
    doc: dict[str, Any], operation: dict[str, Any], status: int
) -> dict[str, Any] | None:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return None
    response_obj = (
        responses.get(str(status))
        or responses.get(f"{status // 100}XX")
        or responses.get(f"{status // 100}xx")
        or responses.get("default")
    )
    response_obj = _resolve_ref(doc, response_obj)
    if not isinstance(response_obj, dict):
        return None
    media = _media_object(response_obj.get("content"))
    schema = _resolve_ref(doc, media.get("schema")) if media else None
    return schema if isinstance(schema, dict) else None


def _expected_statuses(operation: dict[str, Any]) -> list[str]:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return []
    return sorted(str(k) for k in responses)


def _path_to_regex(openapi_path: str) -> re.Pattern[str]:
    escaped = re.escape(openapi_path)
    pattern = re.sub(r"\\\{[^}/]+\\\}", r"[^/]+", escaped)
    return re.compile(f"^{pattern}$")


def _find_operation(
    doc: dict[str, Any], method: str, path: str
) -> tuple[str, dict[str, Any]] | None:
    for op_method, op_path, operation in _iter_openapi_operations(doc):
        if op_method != method.upper():
            continue
        if op_path == path or _path_to_regex(op_path).match(path):
            return op_path, operation
    return None


def _sample_for_schema(doc: dict[str, Any], schema: Any) -> Any:
    schema = _resolve_ref(doc, schema)
    if not isinstance(schema, dict):
        return None
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        props = schema.get("properties")
        if not isinstance(props, dict):
            return {}
        return {str(k): _sample_for_schema(doc, v) for k, v in props.items()}
    if schema_type == "array":
        return [_sample_for_schema(doc, schema.get("items", {}))]
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    return "string"


def _request_body_example(doc: dict[str, Any], operation: dict[str, Any]) -> str | None:
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


def _parameters_for_operation(operation: dict[str, Any]) -> list[dict[str, Any]]:
    params = operation.get("parameters")
    return [p for p in params if isinstance(p, dict)] if isinstance(params, list) else []


def _request_url(base_url: str, path: str, operation: dict[str, Any]) -> str:
    url_path = re.sub(r"\{([^}/]+)\}", r"{{\1}}", path)
    query_params: list[tuple[str, str]] = []
    for param in _parameters_for_operation(operation):
        if param.get("in") == "query" and isinstance(param.get("name"), str):
            query_params.append((str(param["name"]), f"{{{{{param['name']}}}}}"))
    query = urlencode(query_params)
    return f"{base_url}{url_path}{'?' + query if query else ''}"


def _operation_to_item(
    doc: dict[str, Any], base_url: str, method: str, path: str, operation: dict[str, Any]
) -> CollectionItem:
    summary = operation.get("summary") or operation.get("operationId")
    name = str(summary or _operation_key(method, path))
    body = _request_body_example(doc, operation)
    headers = {"content-type": "application/json"} if body else {}
    return CollectionItem(
        id=str(uuid.uuid4()),
        name=name,
        method=method,  # type: ignore[arg-type]
        url=_request_url(base_url, path, operation),
        headers=headers,
        body=body,
    )


def _count_requests(items: list[CollectionItem]) -> int:
    total = 0
    for item in items:
        total += _count_requests(item.items) if item.is_folder else 1
    return total


def _flatten_requests(items: list[CollectionItem]) -> list[CollectionItem]:
    out: list[CollectionItem] = []
    for item in items:
        if item.is_folder:
            out.extend(_flatten_requests(item.items))
        else:
            out.append(item)
    return out


def _json_or_text(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


@router.post("/openapi/import", response_model=OpenApiImportOutput)
def import_openapi(body: OpenApiImportInput) -> OpenApiImportOutput:
    doc = _parse_structured_content(body.content, body.format)
    if "openapi" not in doc and "swagger" not in doc:
        raise HTTPException(status_code=400, detail="document is not an OpenAPI/Swagger spec")
    base_url = _openapi_base_url(doc, body.base_url)
    items = [
        _operation_to_item(doc, base_url, method, path, operation)
        for method, path, operation in _iter_openapi_operations(doc)
    ]
    info = doc.get("info") if isinstance(doc.get("info"), dict) else {}
    name = body.collection_name or str(info.get("title") or "OpenAPI import")
    coll = Collection(id=str(uuid.uuid4()), name=name, version=1, items=items)
    storage._atomic_write(coll)
    return OpenApiImportOutput(
        collection_id=coll.id,
        collection_name=coll.name,
        request_count=_count_requests(coll.items),
    )


@router.get("/openapi/export/{collection_id}", response_model=OpenApiExportOutput)
def export_openapi(collection_id: str) -> OpenApiExportOutput:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    paths: dict[str, dict[str, Any]] = {}
    for req in _flatten_requests(coll.items):
        if not req.url or not req.method:
            continue
        parsed = urlsplit(req.url)
        path = parsed.path or "/"
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key and f"{{{{{key}}}}}" in value:
                pass
        path = re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}", r"{\1}", path)
        operation: dict[str, Any] = {
            "summary": req.name,
            "responses": {"200": {"description": "OK"}},
        }
        if req.body:
            operation["requestBody"] = {
                "content": {
                    "application/json": {
                        "example": _json_or_text(req.body),
                    }
                }
            }
        paths.setdefault(path, {})[req.method.lower()] = operation
    return OpenApiExportOutput(
        openapi={
            "openapi": "3.1.0",
            "info": {"title": coll.name, "version": "1.0.0"},
            "paths": paths,
        }
    )


@router.post("/contracts/validate", response_model=ContractValidateOutput)
def validate_contract(body: ContractValidateInput) -> ContractValidateOutput:
    doc = _parse_structured_content(body.openapi_content)
    found = _find_operation(doc, body.method, body.path)
    if found is None:
        return ContractValidateOutput(
            passed=False,
            violations=[ContractViolation(path="$", message="operation is not documented")],
        )
    openapi_path, operation = found
    expected = _expected_statuses(operation)
    if str(body.status) not in expected and "default" not in expected:
        return ContractValidateOutput(
            passed=False,
            operation_id=operation.get("operationId"),
            expected_statuses=expected,
            violations=[
                ContractViolation(
                    path="$status",
                    message=f"status {body.status} is not one of {', '.join(expected)}",
                )
            ],
        )
    schema = _schema_for_response(doc, operation, body.status)
    if schema is None:
        return ContractValidateOutput(
            passed=True,
            operation_id=operation.get("operationId") or _operation_key(body.method, openapi_path),
            expected_statuses=expected,
        )
    try:
        payload = json.loads(body.body) if body.body else None
    except json.JSONDecodeError as exc:
        return ContractValidateOutput(
            passed=False,
            operation_id=operation.get("operationId"),
            expected_statuses=expected,
            violations=[ContractViolation(path="$body", message=f"invalid JSON: {exc}")],
        )
    try:
        validator = Draft202012Validator(schema)
        violations = [
            ContractViolation(
                path="$" + "".join(f".{p}" for p in error.absolute_path),
                message=error.message,
            )
            for error in sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
        ]
    except SchemaError as exc:
        violations = [ContractViolation(path="$schema", message=str(exc))]
    return ContractValidateOutput(
        passed=len(violations) == 0,
        operation_id=operation.get("operationId") or _operation_key(body.method, openapi_path),
        expected_statuses=expected,
        violations=violations,
    )


@router.post("/contracts/drift", response_model=ContractDriftOutput)
def detect_contract_drift(body: ContractDriftInput) -> ContractDriftOutput:
    doc = _parse_structured_content(body.openapi_content)
    documented = {_operation_key(method, path) for method, path, _ in _iter_openapi_operations(doc)}
    collection_keys: set[str] = set()
    if body.collection_id:
        coll = storage.get(body.collection_id)
        if coll is None:
            raise HTTPException(status_code=404, detail="collection not found")
        for req in _flatten_requests(coll.items):
            if req.method and req.url:
                path = re.sub(
                    r"\{\{\s*([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}",
                    r"{\1}",
                    urlsplit(req.url).path or "/",
                )
                collection_keys.add(_operation_key(req.method, path))
    failing: list[ContractValidateOutput] = []
    passed = 0
    for observed in body.observed:
        result = validate_contract(
            ContractValidateInput(
                openapi_content=body.openapi_content,
                method=observed.method,
                path=observed.path,
                status=observed.status,
                headers=observed.headers,
                body=observed.body,
            )
        )
        if result.passed:
            passed += 1
        else:
            failing.append(result)
    return ContractDriftOutput(
        missing_in_collection=sorted(documented - collection_keys) if body.collection_id else [],
        undocumented_requests=sorted(collection_keys - documented) if body.collection_id else [],
        failing_observations=failing,
        passed_observations=passed,
    )
