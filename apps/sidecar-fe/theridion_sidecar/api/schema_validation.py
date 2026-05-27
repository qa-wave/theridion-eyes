"""Response schema validation — validate JSON against JSON Schema,
auto-generate schemas from sample bodies, and diff two schemas."""

from __future__ import annotations

import json
import re
from typing import Any

import jsonschema
from fastapi import APIRouter, HTTPException
from jsonschema import Draft7Validator, Draft202012Validator
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/schema", tags=["schema"])


# ---- Models ----------------------------------------------------------------


class SchemaValidationError(BaseModel):
    path: str
    message: str
    schema_path: str = ""


class ValidateInput(BaseModel):
    body: str
    json_schema: dict[str, Any] | str = Field(alias="schema")


class ValidateOutput(BaseModel):
    valid: bool
    errors: list[SchemaValidationError] = Field(default_factory=list)


class GenerateInput(BaseModel):
    body: str


class GenerateOutput(BaseModel):
    schema_value: dict[str, Any] = Field(serialization_alias="schema")

    model_config = {"populate_by_name": True}


class SchemaDiffField(BaseModel):
    path: str
    kind: str  # "added", "removed", "changed"
    detail: str = ""


class DiffInput(BaseModel):
    old_schema: dict[str, Any] | str = Field(alias="old")
    new_schema: dict[str, Any] | str = Field(alias="new")


class DiffOutput(BaseModel):
    added: list[SchemaDiffField] = Field(default_factory=list)
    removed: list[SchemaDiffField] = Field(default_factory=list)
    changed: list[SchemaDiffField] = Field(default_factory=list)


# ---- Helpers ---------------------------------------------------------------


def _parse_json(value: str, label: str = "JSON") -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {label}: {exc}") from exc


def _resolve_schema(value: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(value, str):
        parsed = _parse_json(value, "schema")
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="Schema must be a JSON object")
        return parsed
    return value


def _pick_validator(schema: dict[str, Any]) -> type:
    draft = schema.get("$schema", "")
    if "2020-12" in draft:
        return Draft202012Validator
    return Draft7Validator


def _path_str(path: Any) -> str:
    parts: list[str] = []
    for p in path:
        if isinstance(p, int):
            parts.append(f"[{p}]")
        else:
            parts.append(f".{p}" if parts else str(p))
    return "$." + "".join(parts) if parts else "$"


def _schema_path_str(path: Any) -> str:
    return "/".join(str(p) for p in path)


# ---- Validate --------------------------------------------------------------


@router.post("/validate", response_model=ValidateOutput)
def validate_schema(body: ValidateInput) -> ValidateOutput:
    # Parse body JSON
    try:
        data = json.loads(body.body)
    except json.JSONDecodeError as e:
        return ValidateOutput(
            valid=False,
            errors=[SchemaValidationError(path="$", message=f"Invalid JSON: {e}")],
        )

    schema = _resolve_schema(body.json_schema)

    validator_cls = _pick_validator(schema)
    try:
        validator_cls.check_schema(schema)
    except jsonschema.SchemaError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid JSON Schema: {exc.message}"
        ) from exc

    validator = validator_cls(schema)
    errors: list[SchemaValidationError] = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        errors.append(
            SchemaValidationError(
                path=_path_str(err.absolute_path),
                message=err.message,
                schema_path=_schema_path_str(err.absolute_schema_path),
            )
        )
    return ValidateOutput(valid=len(errors) == 0, errors=errors)


# ---- Generate --------------------------------------------------------------

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
_URI_RE = re.compile(r"^https?://")


def _infer_string_format(value: str) -> str | None:
    if _UUID_RE.match(value):
        return "uuid"
    if _EMAIL_RE.match(value):
        return "email"
    if _DATETIME_RE.match(value):
        return "date-time"
    if _DATE_RE.match(value):
        return "date"
    if _URI_RE.match(value):
        return "uri"
    return None


def _generate_schema(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        schema: dict[str, Any] = {"type": "string"}
        fmt = _infer_string_format(value)
        if fmt:
            schema["format"] = fmt
        return schema
    if isinstance(value, list):
        if len(value) == 0:
            return {"type": "array", "items": {}}
        return {"type": "array", "items": _generate_schema(value[0])}
    if isinstance(value, dict):
        properties: dict[str, Any] = {}
        for k, v in value.items():
            properties[k] = _generate_schema(v)
        return {
            "type": "object",
            "properties": properties,
            "required": sorted(value.keys()),
        }
    return {}


@router.post("/generate")
def generate_schema(inp: GenerateInput) -> dict[str, Any]:
    data = _parse_json(inp.body, "body")
    schema = _generate_schema(data)
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    return {"schema": schema}


# ---- Diff ------------------------------------------------------------------


def _collect_properties(
    schema: dict[str, Any], prefix: str = "$"
) -> dict[str, dict[str, Any]]:
    """Flatten schema properties into a path -> sub-schema map."""
    result: dict[str, dict[str, Any]] = {}
    props = schema.get("properties", {})
    for key, sub in props.items():
        path = f"{prefix}.{key}"
        result[path] = sub
        if sub.get("type") == "object":
            result.update(_collect_properties(sub, path))
        elif sub.get("type") == "array" and isinstance(sub.get("items"), dict):
            items = sub["items"]
            items_path = f"{path}[]"
            result[items_path] = items
            if items.get("type") == "object":
                result.update(_collect_properties(items, items_path))
    return result


def _describe_change(old_sub: dict[str, Any], new_sub: dict[str, Any]) -> str:
    changes: list[str] = []
    if old_sub.get("type") != new_sub.get("type"):
        changes.append(f"type: {old_sub.get('type')} -> {new_sub.get('type')}")
    if old_sub.get("format") != new_sub.get("format"):
        changes.append(f"format: {old_sub.get('format')} -> {new_sub.get('format')}")
    old_req = set(old_sub.get("required", []))
    new_req = set(new_sub.get("required", []))
    if old_req != new_req:
        changes.append(f"required: {sorted(old_req)} -> {sorted(new_req)}")
    return "; ".join(changes) if changes else "schema changed"


@router.post("/diff", response_model=DiffOutput)
def diff_schemas(inp: DiffInput) -> DiffOutput:
    old = _resolve_schema(inp.old_schema)
    new = _resolve_schema(inp.new_schema)

    old_fields = _collect_properties(old)
    new_fields = _collect_properties(new)

    old_keys = set(old_fields.keys())
    new_keys = set(new_fields.keys())

    added = [
        SchemaDiffField(
            path=k, kind="added", detail=f"type: {new_fields[k].get('type', '?')}"
        )
        for k in sorted(new_keys - old_keys)
    ]
    removed = [
        SchemaDiffField(
            path=k, kind="removed", detail=f"type: {old_fields[k].get('type', '?')}"
        )
        for k in sorted(old_keys - new_keys)
    ]
    changed: list[SchemaDiffField] = []
    for k in sorted(old_keys & new_keys):
        if old_fields[k] != new_fields[k]:
            changed.append(
                SchemaDiffField(
                    path=k,
                    kind="changed",
                    detail=_describe_change(old_fields[k], new_fields[k]),
                )
            )

    return DiffOutput(added=added, removed=removed, changed=changed)
